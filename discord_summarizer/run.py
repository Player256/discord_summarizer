import os
import discord
import asyncio
import dotenv
from collections import defaultdict
from typing import Dict
from prompts import SYSTEM_PROMPT, PROMPT_FORMATS
from schema import InputSchema
from naptha_sdk.schemas import ToolDeployment, ToolRunInput, NodeConfigUser
from naptha_sdk.user import sign_consumer_id
from naptha_sdk.inference import InferenceClient

dotenv.load_dotenv()
class DiscordSummarizer:
    def __init__(self, bot, tool_deployment: ToolDeployment, tool_inputs: InputSchema):
        self.tool_deployment = tool_deployment
        self.bot = bot
        self.system_prompt = SYSTEM_PROMPT
        self.prompt_formats = PROMPT_FORMATS
        self.max_entries = tool_inputs.max_entries

        self.node = NodeConfigUser(
            ip=self.tool_deployment.node.ip,
            http_port=None,
            server_type="https"
        )
        self.inference_client = InferenceClient(self.node)

    async def summarize_channel(self, channel_id):
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return "Channel not found."

        main_messages = []
        threads = defaultdict(list)

        async for message in channel.history(limit=self.max_entries):
            if message.thread:
                threads[message.thread.id].append(message)
            else:
                main_messages.append(message)

        summary = f"Summary of #{channel.name}:\n\n"
        summary += await self._summarize_messages(main_messages, "Main Channel")

        for thread_id, thread_messages in threads.items():
            thread = channel.get_thread(thread_id)
            if thread:
                thread_summary = await self._summarize_messages(
                    thread_messages, f"Thread: {thread.name}"
                )
                summary += f"\n{thread_summary}"

        return summary

    async def _summarize_messages(self, messages, context):
        user_message_counts = defaultdict(int)
        file_types = defaultdict(int)
        content_chunks = []

        for message in messages:
            user_message_counts[message.author.name] += 1
            for attachment in message.attachments:
                file_type = attachment.filename.split(".")[-1].lower()
                file_types[file_type] += 1

            content_chunks.append(f"{message.author.name}: {message.content}")

        summary = f"{context}\n"
        summary += "Participants:\n"
        for user, count in user_message_counts.items():
            summary += f"- {user}: {count} messages\n"

        if file_types:
            summary += "\nShared Files:\n"
            for file_type, count in file_types.items():
                summary += f"- {file_type}: {count} files\n"

        content_summary = await self._process_chunks(content_chunks, context)
        summary += f"\nContent Summary:\n{content_summary}\n"

        return summary

    async def _process_chunks(self, chunks, context, tool_run_input):
        prompt = self.prompt_formats.format(
            context=context,
            content="\n".join(
                reversed(chunks)
            ),  
        )

        system_prompt = self.system_prompts.replace(
            "{persona_intensity}", str(self.bot.persona_intensity)
        )

        # OpenAI API format
        messages = [
            {"role" : "system","content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        try:
            response = asyncio.run(
                self.inference_client.run(
                    {
                        "model": self.tool_deployment.config.llm_config.model,
                        "messages": messages,
                        "temperature": self.tool_deployment.config.llm_config.temperature,
                        "max_tokens": self.deplotool_deploymentyment.config.llm_config.max_tokens,
                    }
                )
            )
            
            if isinstance(response, dict):
                response = response['choices'][0]['message']['content']
            else:
                response = response.choices[0].message.content
            return response  
            
        except Exception as e:
            return f"Error in generating summary: {str(e)}"

async def run(module_run: Dict):
    intents = discord.Intents.default()
    intents.message_content = True
    bot = discord.Client(intents=intents)
    module_run = ToolRunInput(**module_run)
    module_run.inputs = InputSchema(**module_run.inputs)
    DiscordSummarizerTool = DiscordSummarizer(bot,module_run, module_run.inputs)
    method = getattr(DiscordSummarizerTool, module_run.inputs.tool_name, None)
    if not method:
        raise ValueError(f"Method {module_run.inputs.tool_name} not found")
    
    #For testing the module
    if module_run.inputs.tool_name == "_summarize_messages":
        method(module_run.inputs.messages, "Main Channel")
    else:
        method(module_run.inputs.channel_id)


if __name__ == "__main__":
    from naptha_sdk.client.naptha import Naptha
    from naptha_sdk.configs import setup_module_deployment

    naptha = Naptha()

    deployment = asyncio.run(
        setup_module_deployment(
            "tool",
            "discord_summarizer/configs/deployment.json",
            node_url=os.getenv("NODE_URL"),
        )
    )

    input_params_1 = {
        "tool_name" : "summarize_messages",
        "messages": [
            {
                "author": {"name": "Alice"},
                "content": "Hello, how are you?",
            },
            {
                "author": {"name": "Bob"},
                "content": "I'm good, thanks! How about you?",
            }
        ]
        
    }

    module_run = {
        "inputs": input_params_1,
        "deployment": deployment,
        "consumer_id": naptha.user.id,
        "signature": sign_consumer_id(
            naptha.user.id, os.getenv("PRIVATE_KEY_FULL_PATH")
        ),
    }

    response = asyncio.run(run(module_run))

    print("Response:",response)  
