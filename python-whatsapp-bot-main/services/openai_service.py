import os
import logging
from typing import Optional
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def generate_response(prompt: str) -> Optional[str]:
    """Generate AI response using OpenAI Assistant"""
    try:
        # Create conversation thread
        thread = client.beta.threads.create()
        
        # Add user message
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=prompt
        )

        # Start assistant process
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=os.environ.get("OPENAI_ASSISTANT_ID")
        )

        # Wait for completion (simple polling)
        while True:
            run_status = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
            if run_status.status in ["completed", "failed"]:
                break

        if run_status.status == "failed":
            logging.error(f"OpenAI Error: {run_status.last_error}")
            return None

        # Retrieve and return assistant's response
        messages = client.beta.threads.messages.list(thread_id=thread.id)
        for message in messages:
            if message.role == "assistant":
                return message.content[0].text.value

        return "I couldn't generate a response. Please try again."

    except Exception as e:
        logging.error(f"OpenAI API Error: {str(e)}")
        return None