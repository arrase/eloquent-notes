import base64
import requests
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_ollama import ChatOllama

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

def send_audio_to_ollama(ollama_url, model, system_prompt, user_prompt, context_length, wav_file_path):
    with open(wav_file_path, "rb") as f:
        audio_bytes = f.read()
    
    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
    
    num_ctx = context_length or get_model_max_context(ollama_url, model)
    
    llm_kwargs = {
        "base_url": ollama_url,
        "model": model,
        "temperature": 0.0
    }
    if num_ctx:
        llm_kwargs["num_ctx"] = num_ctx
        
    llm = ChatOllama(**llm_kwargs)
    
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
    
    response = llm.invoke(messages)
    return response.content
