# Dockerfile -> Image -> Container
# use python 3.9
FROM python:3.9

# set working dir
WORKDIR /api

# copy all files and folders
COPY . /api/
#COPY ./requirements.txt /api/requirements.txt

# install dependency
RUN pip install --no-cache-dir --upgrade -r /api/requirements.txt

# run the script
CMD ["python", "wsgi.py"]
