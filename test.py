import torch
import transformers

print(torch.cuda.is_available())  # True
print(torch.cuda.get_device_name(0))  # GeForce RTX 4080 등 출력

model_id = "MLP-KTLim/llama-3-Korean-Bllossom-8B"

pipe = transformers.pipeline(
    "text-generation",
    model=model_id,
    model_kwargs={"torch_dtype": "auto"},
    device_map="auto"
)

while True:
    user_input = input("나: ")
    if user_input.lower() in ["exit", "quit", "종료"]:
        print("챗봇을 종료합니다.")
        break
    response = pipe(
        user_input,
        max_new_tokens=512,
        do_sample=True,
        temperature=0.6,
        top_p=0.9
    )
    answer = response[0]["generated_text"][len(user_input):].strip()
    print("Llama-3:", answer)