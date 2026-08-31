def openai_answer(question):

    url = "https://api.openai.com/v1/responses"

    system_text = """
Siz "Madaniy Meros AI" nomli yordamchisiz.

Siz O'zbekiston madaniy merosi,
tarixiy-me'moriy obidalari,
madaniy meros obyektlarini muhofaza qilish,
restavratsiya,
ta'mirlash,
moslashtirish,
me'moriy yechimlar,
loyiha hujjatlari va ilmiy-ekspert kengashi
bilan bog'liq savollarga yordam berasiz.

Javoblarni o'zbek tilida bering.

Javob:
- aniq;
- tushunarli;
- amaliy;
- imkon qadar qisqa;
- kerak bo'lsa punktlar bilan bo'lsin.

Huquqiy masalalarda qonun yoki qaror raqamini
aniq bilmasangiz, o'ylab topmang.
Noaniq ma'lumotni fakt sifatida bermang.
"""

    data = {
        "model": OPENAI_MODEL,
        "instructions": system_text,
        "input": question
    }

    headers = {
        "Authorization": "Bearer " + OPENAI_API_KEY,
        "Content-Type": "application/json"
    }

    result = http_json(
        url,
        data=data,
        headers=headers,
        timeout=OPENAI_TIMEOUT
    )

    answer = result.get("output_text", "")

    if not answer:
        return "OpenAI javob qaytarmadi."

    return answer.strip()
