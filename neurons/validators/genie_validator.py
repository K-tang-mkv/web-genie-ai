import os
import bittensor as bt
import numpy as np
import random
import threading
import time

from datetime import datetime, timedelta
from typing import Union

from webgenie.base.neuron import BaseNeuron
from webgenie.constants import (
    MAX_COMPETETION_HISTORY_SIZE, 
    MAX_SYNTHETIC_TASK_SIZE, 
    WORK_DIR,
    LIGHTHOUSE_SERVER_WORK_DIR,
    TASK_REVEAL_TIME,
    TASK_REVEAL_TIMEOUT,
    SESSION_WINDOW_BLOCKS,
    BLOCK_IN_SECONDS,
)
from webgenie.challenges import (
    AccuracyChallenge,
    QualityChallenge,
    SeoChallenge,
)
from webgenie.helpers.htmls import preprocess_html, is_valid_resources
from webgenie.helpers.images import image_debug_str
from webgenie.protocol import (
    WebgenieImageSynapse, 
    WebgenieTextSynapse,
    verify_answer_hash,
)
from webgenie.storage import store_results_to_database
from webgenie.tasks import Solution
from webgenie.tasks.metric_types import (
    ACCURACY_METRIC_NAME, 
    QUALITY_METRIC_NAME,
    SEO_METRIC_NAME,
)
from webgenie.tasks.image_task_generator import ImageTaskGenerator
from webgenie.utils.uids import get_all_available_uids


class GenieValidator:
    def __init__(self, neuron: BaseNeuron):
        self.neuron = neuron
        self.lock = neuron.lock
        self.config = neuron.config
        self.miner_results = []
        self.synthetic_tasks = []

        self.task_generators = [
            (ImageTaskGenerator(), 1.0), # currently only image task generator is supported
        ]

    async def query_miners(self):
        try:
            with self.lock:
                if len(self.miner_results) > MAX_COMPETETION_HISTORY_SIZE:
                    bt.logging.info(
                        f"Competition history size {len(self.miner_results)} "
                        f"exceeds max size {MAX_COMPETETION_HISTORY_SIZE}, skipping"
                    )
                    return
                
                if not self.synthetic_tasks:
                    bt.logging.info("No synthetic tasks available, skipping")
                    return

                task, synapse = self.synthetic_tasks.pop(0)

            bt.logging.info("querying miners")
            miner_uids = get_all_available_uids(self.neuron)
            if len(miner_uids) == 0:
                bt.logging.warning("No miners available")
                return
            
            available_challenges_classes = [
                AccuracyChallenge, 
                QualityChallenge, 
                SeoChallenge,
            ]  
            
            with self.lock:
                session_number = self.neuron.session_number

            challenge_class = available_challenges_classes[session_number % len(available_challenges_classes)]
            challenge = challenge_class(task=task, session_number=session_number)

            synapse.competition_type = challenge.competition_type

            bt.logging.debug(f"Querying {len(miner_uids)} miners")
            
            query_time = time.time()
            async with bt.dendrite(wallet=self.neuron.wallet) as dendrite:
                all_synapse_hash_results = await dendrite(
                    axons = [self.neuron.metagraph.axons[uid] for uid in miner_uids],
                    synapse=synapse,
                    timeout=task.timeout,
                )
         
            elapsed_time = time.time() - query_time
            sleep_time_before_reveal = max(0, task.timeout - elapsed_time) + TASK_REVEAL_TIME
            time.sleep(sleep_time_before_reveal)

            bt.logging.debug(f"Revealing task {task.task_id}")
            
            async with bt.dendrite(wallet=self.neuron.wallet) as dendrite:
                all_synapse_reveal_results = await dendrite(
                    axons = [self.neuron.metagraph.axons[uid] for uid in miner_uids],
                    synapse=synapse,
                    timeout=TASK_REVEAL_TIMEOUT,
                )
            
            solutions = []
            for reveal_synapse, hash_synapse, miner_uid in zip(all_synapse_reveal_results, all_synapse_hash_results, miner_uids):
                reveal_synapse.html_hash = hash_synapse.html_hash
                checked_synapse = await self.checked_synapse(reveal_synapse)
                if checked_synapse is not None:
                    solutions.append(
                        Solution(
                            html = checked_synapse.html, 
                            miner_uid = miner_uid, 
                        )
                    )
            challenge.solutions = solutions

            bt.logging.info(f"Received {len(solutions)} valid solutions")
            with self.lock:
                self.miner_results.append(challenge)

        except Exception as e:
            bt.logging.error(f"Error in query_miners: {e}")
            raise e

    async def score(self):
        with self.lock:
            if not self.miner_results:
                bt.logging.info("No miner results to score")
                return

            challenge = self.miner_results.pop(0)

        if not challenge.solutions:
            bt.logging.info("No solutions to score")
            return
        
        with self.lock:
            if challenge.session_number != self.neuron.session_number:
                bt.logging.info(
                    f"Session number mismatch: {challenge.session_number} != {self.neuron.session_number}"
                    f"This is the previous session's challenge, skipping"
                )
                return
        
        bt.logging.info(
            f"Scoring - Session number: {challenge.session_number}, "
            f"Competition type: {challenge.competition_type}, "
            f"Task source: {challenge.task.src}"
        )
        
        solutions = challenge.solutions
        miner_uids = [solution.miner_uid for solution in solutions]
        aggregated_scores, scores = await challenge.calculate_scores()
        
        bt.logging.success(f"Task Source: {challenge.task.src}")
        bt.logging.success(f"Competition Type: {challenge.competition_type}")
        bt.logging.success(f"Scores: {scores}")
        bt.logging.success(f"Final scores for {miner_uids}: {aggregated_scores}")
        
        with self.lock:
            self.neuron.score_manager.update_scores(
                aggregated_scores, 
                miner_uids, 
                challenge.session_number,
            )

        with self.lock:
            current_block = self.neuron.block
            session_number = self.neuron.session_number
            session_start_block = session_number * SESSION_WINDOW_BLOCKS
            session_start_datetime = (
                datetime.now() - 
                timedelta(
                    seconds=(current_block - session_start_block) * BLOCK_IN_SECONDS
                )
            )
            payload = {
                "validator": {
                    "hotkey": self.neuron.metagraph.axons[self.neuron.uid].hotkey,
                    "coldkey": self.neuron.metagraph.axons[self.neuron.uid].coldkey,
                },
                "miners": [
                    {
                        "coldkey": self.neuron.metagraph.axons[miner_uids[i]].coldkey,
                        "hotkey": self.neuron.metagraph.axons[miner_uids[i]].hotkey,
                    } for i in range(len(miner_uids))
                ],
                "solutions": [
                    {
                        "miner_answer": { "html": solution.html },
                    } for solution in solutions
                ],
                "scores": [
                    {
                        "aggregated_score": aggregated_scores[i],
                        "accuracy": scores[ACCURACY_METRIC_NAME][i],
                        "seo": scores[SEO_METRIC_NAME][i],
                        "code_quality": scores[QUALITY_METRIC_NAME][i],
                    } for i in range(len(miner_uids))
                ],
                "challenge": {
                    "task": challenge.task.ground_truth_html,
                    "competition_type": challenge.competition_type,
                    "session_number": challenge.session_number,
                },
                "session_start_datetime": session_start_datetime,
            }

        try:
            bt.logging.info(f"Storing results to database: {payload}")
            store_results_to_database(payload)
        except Exception as e:
            bt.logging.error(f"Error storing results to database: {e}")

    async def synthensize_task(self):
        try:
            with self.lock:
                if len(self.synthetic_tasks) > MAX_SYNTHETIC_TASK_SIZE:
                    bt.logging.info(
                        f"Synthetic task size {len(self.synthetic_tasks)} exceeds "
                        f"max size {MAX_SYNTHETIC_TASK_SIZE}, skipping"
                    )
                    return

            bt.logging.info(f"Synthensize task")
            
            task_generator, _ = random.choices(
                self.task_generators,
                weights=[weight for _, weight in self.task_generators],
            )[0]
            
            task, synapse = await task_generator.generate_task()
            with self.lock:
                self.synthetic_tasks.append((task, synapse))

            bt.logging.success(f"Successfully generated task for {task.src}")
        
        except Exception as e:
            bt.logging.error(f"Error in synthensize_task: {e}")

    async def organic_forward(self, synapse: Union[WebgenieTextSynapse, WebgenieImageSynapse]):
        if isinstance(synapse, WebgenieTextSynapse):
            bt.logging.debug(f"Organic text forward: {synapse.prompt}")
            bt.logging.info("Not supported yet.")
            synapse.html = "Not supported yet."
            return synapse
        else:
            bt.logging.debug(f"Organic image forward: {image_debug_str(synapse.base64_image)}...")

        all_miner_uids = get_all_available_uids(self.neuron)
        try:
            if not all_miner_uids:
                raise Exception("No miners available")
            
            query_time = time.time()
            async with bt.dendrite(wallet=self.neuron.wallet) as dendrite:
                responses = await dendrite(
                    axons=[self.neuron.metagraph.axons[uid] for uid in all_miner_uids],
                    synapse=synapse,
                    timeout=synapse.timeout,
                )

            elapsed_time = time.time() - query_time
            sleep_time_before_reveal = max(0, synapse.timeout - elapsed_time) + TASK_REVEAL_TIME
            time.sleep(sleep_time_before_reveal)

            async with bt.dendrite(wallet=self.neuron.wallet) as dendrite:
                responses = await dendrite(
                    axons=[self.neuron.metagraph.axons[uid] for uid in all_miner_uids],
                    synapse=synapse,
                    timeout=TASK_REVEAL_TIMEOUT,
                )

            # Sort miner UIDs and responses by incentive scores
            incentives = self.neuron.metagraph.I[all_miner_uids]
            sorted_indices = np.argsort(-incentives)  # Negative for descending order
            all_miner_uids = [all_miner_uids[i] for i in sorted_indices]
            
            responses = [responses[i] for i in sorted_indices]
            for response in responses:
                checked_synapse = await self.checked_synapse(response)
                if checked_synapse is None:
                    continue
                return checked_synapse
            
            raise Exception(f"No valid solution received")
        except Exception as e:
            bt.logging.error(f"[forward_organic_synapse] Error querying dendrite: {e}")
            synapse.html = f"Error: {e}"
            return synapse
    
    async def checked_synapse(self, synapse: bt.Synapse) -> bt.Synapse:
        if synapse.dendrite.status_code == 200:
            if not verify_answer_hash(synapse):
                bt.logging.warning(f"Invalid answer hash: {synapse.html_hash}")
                return None

            html = preprocess_html(synapse.html)
            if not html or not is_valid_resources(html):
                bt.logging.warning(f"Invalid html or resources: {html}")
                return None

            synapse.html = html
            return synapse
        return None
