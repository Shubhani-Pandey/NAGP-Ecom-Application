FROM python:3.9-slim
COPY requirements.txt /orderapp/requirements.txt
WORKDIR /orderapp
RUN pip install -r requirements.txt
COPY . /orderapp
EXPOSE 5001
ENTRYPOINT ["python"]
CMD ["python","app.py"]