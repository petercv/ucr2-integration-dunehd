FROM python:3.11-slim-bullseye
WORKDIR /app
COPY ./requirements.txt requirements.txt
RUN pip3 install --no-cache-dir --upgrade -r requirements.txt
ADD . .
CMD ["python3", "-u", "intg-dunehd/driver.py"]