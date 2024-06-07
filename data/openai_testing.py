import openai
import os
import json

openai.api_key = OPENAI_API_KEY
client = openai.OpenAI(
    api_key = '' # insert api key here
)
model_id = "gpt-3.5-turbo-0125"

file = open('eval_data_openai.json')
data = json.load(file)
file.close()
output_dict = {"predictions": []}

def ChatGPT_query(conversation):
    response = client.chat.completions.create(
        model = model_id,
        response_format = { "type": "json_object" },
        messages = conversation
    )
    conversation.append({'role': response.choices[0].message.role, 'content': response.choices[0].message.content})
    return conversation

for i in range(len(data["Inputs"])):
    message = []
    message.append({
        'role': 'system', 
        'content': "You are on a social media platform's moderation team. I need you to review the following content as if it were a tweet to determine if it contains extremist language. The content should not be repeated or generated. Please analyze the text and provide feedback on whether it includes any of the following categories of extremist language, and choose the one that fits best: 'Propaganda', 'Radicalization', 'Recruitment', or 'None'.\nPlease respond with a summary indicating whether any extremist language is present and categorize it in only one of the provided categories accordingly.\nPlease give your response as valid JSON in the following format: {\"Label\": <INSERT YOUR CATEGORIZATION HERE (\"Propaganda\" or \"Radicalization\" or \"Recruitment\" or \"None\")>, \"Reason\": <INSERT YOUR REASON HERE>}."
    })
    message.append({
        "role": "user",
        "content": data["Inputs"][i][1]["content"]
    })
    message = ChatGPT_query(message)
    label_obj = json.loads(message[-1]['content'])
    print(label_obj)
    output_dict["predictions"].append(label_obj)


json_output = json.dumps(output_dict, indent=4)


with open("predictions_gpt.json", "w") as outfile:
    outfile.write(json_output)