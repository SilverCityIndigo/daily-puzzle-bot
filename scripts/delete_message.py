"""One-off: delete a message the bot sent. Usage: python scripts/delete_message.py MESSAGE_ID"""
import asyncio
import os
import sys

import discord


async def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/delete_message.py MESSAGE_ID")
    message_id = int(sys.argv[1])
    token = os.environ["DISCORD_TOKEN"]
    channel_id = int(os.environ["CHANNEL_ID"])
    client = discord.Client(intents=discord.Intents.default())

    @client.event
    async def on_ready():
        channel = client.get_channel(channel_id)
        if channel is None:
            raise SystemExit(f"Channel {channel_id} not found")
        msg = await channel.fetch_message(message_id)
        if msg.author.id != client.user.id:
            raise SystemExit("That message was not sent by this bot")
        await msg.delete()
        print(f"Deleted message {message_id}")
        await client.close()

    async with client:
        await client.start(token)


if __name__ == "__main__":
    asyncio.run(main())
