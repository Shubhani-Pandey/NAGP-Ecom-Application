FROM python:3.8
COPY requirements.txt /userapp/requirements.txt
WORKDIR /userapp
RUN pip install -r requirements.txt
COPY . /userapp
EXPOSE 5003
ENTRYPOINT ["python"]
CMD ["app.py"]