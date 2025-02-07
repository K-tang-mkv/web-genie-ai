import bittensor as bt
from pydantic import BaseModel, Field

from webgenie.base.neuron import BaseNeuron
from webgenie.helpers.llms import openai_call
from webgenie.protocol import WebgenieTextSynapse, WebgenieImageSynapse
import base64
import os

class HTML(BaseModel):
    html: str


class OpenaiMiner:
    def __init__(self, neuron: BaseNeuron):
        self.neuron = neuron

    async def forward_text(self, synapse: WebgenieTextSynapse) -> WebgenieTextSynapse:  
        raise Exception("Not Supported yet.")
        try:  
            html_response = await openai_call(
                messages = [
                    {"role": "system", "content": "You are an expert web developer who specializes in HTML and CSS. A user will provide you with the webpage requirements. You need to return a single html file that uses HTML and CSS to satisfy the requirements. Include all CSS code in the HTML file itself. If it involves any images, use 'rick.jpg' as the placeholder. Do not hallucinate any dependencies to external files. You do not need to include JavaScript scripts for dynamic interactions. Pay attention to things like size, text, position, and color of all the elements, as well as the overall layout. Respond with the content of the HTML+CSS file:"},
                    {"role": "user", "content": "Create a webpage with a red background and a blue rectangle in the center."},
                ], 
                response_format = HTML,
            )
            synapse.html = html_response.html
            return synapse
        except Exception as e:
            bt.logging.error(f"Error in OpenaiMiner forward_text: {e}")
            synapse.html = f"Error in OpenaiMiner forward_text: {e}"
            return synapse

    async def forward_image(self, synapse: WebgenieImageSynapse) -> WebgenieImageSynapse:
        try:
            task_id = synapse.task_id
            base64_img = synapse.base64_image

            # 目标文件路径 (以 .png 为例)
            os.makedirs("/root/web-genie-ai/saved_task_imgs_new", exist_ok=True)
            image_filename = f"/root/web-genie-ai/saved_task_imgs_new/{task_id}.png"

            # 将 base64 转换为二进制数据并保存为文件
            # with open(image_filename, "wb") as image_file:
            #     image_file.write(base64.b64decode(base64_img))
            bt.logging.info(f"task {task_id} saved into /root/web-genie-ai/saved_task_imgs_new")
            html_response = await openai_call(
                messages =  [
                    {
                        "role": "system", 
                        "content": """You are an expert web developer who specializes in HTML and CSS. A user will provide you with the webpage requirements. You need to return a single html file that uses HTML and CSS to satisfy the requirements. Include all CSS code in the HTML file itself. If it involves any images, use 'rick.jpg' as the placeholder. Do not hallucinate any dependencies to external files. You do not need to include JavaScript scripts for dynamic interactions. Pay attention to things like size, text, position, and color of all the elements, as well as the overall layout. Respond with the content of the HTML+CSS file.
                            You should refer to the following criteria to generate a HTML file:
                            1. Semantic HTML: Use appropriate HTML tags to convey meaning. weight: 20
                            2. Accessibility: Ensure content is usable for all, including those with disabilities. weight: 15
                            3. Clean and Readable Code: Maintain consistent formatting and meaningful naming conventions. weight: 10
                            4. Responsive Design: Implement designs that adapt to various screen sizes.  weight: 12
                            5. Performance Optimization: Minimize file sizes and optimize selectors for faster loading. weight: 10
                            6. Cross-Browser Compatibility: Ensure consistent rendering across different browsers. weight: 8
                            7. Validation: Use W3C validators to check for errors and deprecated elements. weight: 7
                            8. Maintainability: Structure code for easy updates and modifications.  weight: 8
                            9. Use of Best Practices: Avoid anti-patterns like excessive specificity and inline styles. weight: 5
                            10. Documentation: Provide clear documentation for styles and design choices. weight: 5
                            
                            **Don't output any other info, only Respond with the content of the HTML+CSS**, for example **output format**:
                            ```
                            <!DOCTYPE html>
                            <html lang="en">
                            ...
                            </html>
                            ```
                        """
                    },
                    {
                        "role": "user",
                        "content": [{
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{synapse.base64_image}",
                            },
                        }],
                    },
                ],
                response_format = HTML,
            )
            html_filename = f"/root/web-genie-ai/saved_task_imgs_new/{task_id}.html"
                
                # 保存 HTML 文件
            # with open(html_filename, "w", encoding="utf-8") as html_file:
            #     html_file.write(html_response)
            
            bt.logging.info(f"HTML content saved as {html_filename}")
            synapse.html = html_response
            return synapse
        except Exception as e:
            bt.logging.error(f"Error in OpenaiMiner forward_image: {e}")
            synapse.html = f"Error in OpenaiMiner forward_image: {e}"
            return synapse