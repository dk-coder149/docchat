# Python का आधिकारिक हल्का वर्शन इस्तेमाल कर रहे हैं
FROM python:3.10-slim

# वर्किंग directorio सेट करें
WORKDIR /app

# पहले requirements फ़ाइल कॉपी करें ताकि कैचिंग का फायदा मिले
COPY requirements.txt .

# डिपेंडेंसीज़ इंस्टॉल करें
RUN pip install --no-cache-dir -r requirements.txt

# बाकी का पूरा प्रोजेक्ट कोड कॉपी करें
COPY . .

# पोर्ट सेट करें जिस पर ऐप रन होगा
EXPOSE 8000

# FastAPI ऐप को uvicorn के जरिए शुरू करने की कमांड
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]