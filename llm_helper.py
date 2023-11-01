def greeting_tool(input: str) -> str:
        greetings = ["hi", "hello", "good morning", "good afternoon"]
        if input.lower() in greetings:
            return "Hello there!"
        else:
            return "I don't understand your greeting."
        
def explanation_tool(input: str) -> str:
    query = ["who are you", "what are you", "what do you do", "what is your use"]
    if input.lower() in query:
        return "I am ChatVM, your assistant in understanding the large volume of surveillance and customer traffic data! Feel free to ask queries on what has happened within your establishment."
    else:
        return "I am ChatVM, your assistant in understanding the large volume of surveillance and customer traffic data! Feel free to ask queries on what has happened within your establishment."
