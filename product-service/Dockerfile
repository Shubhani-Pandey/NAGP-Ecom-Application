FROM python:3.9-slim
COPY requirements.txt /productapp/requirements.txt
WORKDIR /productapp
RUN pip install -r requirements.txt
COPY . /productapp
EXPOSE 5002
ENTRYPOINT ["python"]
CMD ["python", "app.py"]