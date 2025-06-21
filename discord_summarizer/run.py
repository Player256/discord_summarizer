from naptha_sdk.modules.tool import Tool
from naptha_sdk.schemas import ToolDeployment, ToolRunInput, ToolRunOutput
from naptha_sdk.user import sign_consumer_id
from agent.cache_manager import CacheManager
from collections import defaultdict
import os

class ChannelSummarizerTool(Tool):
    async def create(self, deployment: ToolDeployment, *args, **kwargs):
        self.deployment = deployment
        self.max_entries = deployment.config.get("max_entries", 100)
        self.cache_manager = CacheManager()

        self.llm_tool = Tool()
        await self.llm_tool.create(deployment=deployment.tool_deployments[0])

    async def run(self, tool_run_input: ToolRunInput, *args, **kwargs):
        channel_id = tool_run_input.inputs.get("channel_id")
        bot = tool_run_input.inputs.get("bot")

        if not channel_id or not bot:
            return ToolRunOutput(results="channel_id and bot are required inputs.")

        channel = bot.get_channel(channel_id)
        if not channel:
            return ToolRunOutput(results="Channel not found.")

        main_messages = []
        threads = defaultdict(list)

        async for message in channel.history(limit=self.max_entries):
            if message.thread:
                threads[message.thread.id].append(message)
            else:
                main_messages.append(message)

        summary = f"Summary of #{channel.name}:\n\n"
        summary += await self._summarize_messages(
            main_messages, "Main Channel", tool_run_input.consumer_id
        )

        for thread_id, thread_messages in threads.items():
            thread = channel.get_thread(thread_id)
            if thread:
                thread_summary = await self._summarize_messages(
                    thread_messages,
                    f"Thread: {thread.name}",
                    tool_run_input.consumer_id,
                )
                summary += f"\n{thread_summary}"

        self.cache_manager.append_to_conversation(str(channel_id), {"summary": summary})
        return ToolRunOutput(results=summary)

    async def _process_chunks(self, chunks, context, consumer_id):
        prompt = (
            f"Summarize the following Discord channel:\nContext: {context}\nContent:\n"
            + "\n".join(reversed(chunks))
        )

        llm_tool_run_input = ToolRunInput(
            consumer_id=consumer_id,
            inputs={
                "prompt": prompt,
                "system_prompt": "You are a helpful assistant that summarizes Discord conversations.",
            },
            deployment=self.deployment.tool_deployments[0],
            signature=sign_consumer_id(consumer_id, os.getenv("PRIVATE_KEY_FULL_PATH")),
        )

        try:
            tool_response = await self.llm_tool.run(llm_tool_run_input)
            return tool_response.results
        except Exception as e:
            return f"Error in generating summary: {str(e)}"

    async def _summarize_messages(self, messages, context, consumer_id):
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

        content_summary = await self._process_chunks(
            content_chunks, context, consumer_id
        )
        summary += f"\nContent Summary:\n{content_summary}\n"

        return summary