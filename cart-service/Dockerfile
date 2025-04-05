FROM python:3.8
COPY requirements.txt /cartapp/requirements.txt
WORKDIR /cartapp
RUN pip install -r requirements.txt
COPY . /cartapp
ENTRYPOINT ["python"]
CMD ["python","app.py"]