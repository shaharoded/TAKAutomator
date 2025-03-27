from openai import OpenAI
import tiktoken
from typing import Union

# Local Code
from secret_keys import OPENAI_API_KEYS
from Config.agent_config import AgentConfig


# Set your OpenAI API key in a SecretKeys.py file
client = OpenAI(api_key=OPENAI_API_KEYS.get('shahar_personal_key'))
TOKENIZER = tiktoken.encoding_for_model("gpt-4")


class LLMAgent:
    '''
    LLM based agent responsible for assisting based on predefined prompts.
    '''
    def __init__(self):
        """
        Initialize the LLMAgent instance. 
        Agent is responsible for the generation of the TAK (.xml) strings.
        """
        self.engine = AgentConfig.OPENAI_ENGINE
        self.temperature = AgentConfig.TEMPERATURE
        self.system_prompt = AgentConfig.SYSTEM_PROMPT

    
    def count_tokens(self, text: str) -> int:
        """
        Assess the number of tokens in a text.
        For business purpose. This will not bill the API account.
        """
        encoding = TOKENIZER.encode(text)
        token_count = len(encoding)
        print(f"[Info]: Number of input tokens are: {token_count}")
        return token_count


    def generate_response(self, input_text: str) -> Union[str, dict]:
        """
        Generate a response for a single prompt using the OpenAI API.
        This will activate and bill the API account.
        
        Args:
            input_text (str): The input text to process
            
        Returns:
            str or dict: The generated response from the LLM, as string or parsed JSON object
                         depending on the response_format setting
        """
        messages = []
        if self.system_prompt:
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": input_text}
            ]
        else:
            messages = [
                {"role": "user", "content": input_text}
            ]
        
        # Create response format parameter if specified
        response_format_param = None
        if self.response_format == 'json':
            response_format_param = {"type": "json_object"}
        elif self.response_format != 'text':
            response_format_param = {"type": self.response_format}
        
        # Build the API call parameters
        api_params = {
            "model": self.engine,
            "messages": messages,
            "temperature": self.temperature
        }
        
        # Add response format if specified
        if response_format_param:
            api_params["response_format"] = response_format_param
        
        # Make the API call
        response = client.chat.completions.create(**api_params)
        raw_response = response.choices[0].message.content
        
        # Return raw text for non-JSON responses
        return raw_response