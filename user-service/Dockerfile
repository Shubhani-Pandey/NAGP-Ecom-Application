FROM python:3.9-slim
COPY requirements.txt /userapp/requirements.txt
WORKDIR /userapp
RUN pip install -r requirements.txt
COPY . /userapp
EXPOSE 5001
ENTRYPOINT ["python"]
CMD ["python","app.py"]