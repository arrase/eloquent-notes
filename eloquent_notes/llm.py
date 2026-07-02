import base64
import requests
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_ollama import ChatOllama

class NoteResponse(BaseModel):
    empty: bool = Field(description="True if the audio contains only silence, background noise, or no spoken words; False otherwise.")
    text: str = Field(description="Cleaned, polished, and structured Markdown text if audio is not empty; empty string otherwise.")


def get_model_max_context(ollama_url, model):
    try:
        response = requests.post(
            f"{ollama_url}/api/show",
            json={"name": model},
            timeout=5
        )
        response.raise_for_status()
        info = response.json().get("model_info", {})
        for k, v in info.items():
            if k.endswith(".context_length"):
                return int(v)
    except (requests.RequestException, ValueError, KeyError):
        pass
    return None

def preload_model(ollama_url, model, keep_alive="5m"):
    """
    Sends a request to Ollama to preload the model into memory.
    This reduces the cold start time when the user stops recording and triggers generation.
    """
    try:
        response = requests.post(
            f"{ollama_url}/api/chat",
            json={
                "model": model,
                "messages": [],
                "keep_alive": keep_alive
            }
        )
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        raise Exception(f"Failed to preload model: {e}")

def send_audio_to_ollama(ollama_url, model, system_prompt, user_prompt, context_length, wav_file_path, keep_alive="5m"):
    with open(wav_file_path, "rb") as f:
        audio_bytes = f.read()
    
    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
    
    num_ctx = context_length or get_model_max_context(ollama_url, model)
    
    llm_kwargs = {
        "base_url": ollama_url,
        "model": model,
        "temperature": 0.0,
        "keep_alive": keep_alive
    }
    if num_ctx:
        llm_kwargs["num_ctx"] = num_ctx
        
    llm = ChatOllama(**llm_kwargs)
    structured_llm = llm.with_structured_output(NoteResponse)
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=[
                {"type": "text", "text": user_prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:audio/wav;base64,{audio_base64}"}
                }
            ]
        )
    ]
    
    response = structured_llm.invoke(messages)
    return {
        "empty": response.empty,
        "text": response.text
    }
