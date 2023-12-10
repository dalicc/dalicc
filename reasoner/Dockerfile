#FROM continuumio/miniconda3
FROM tiangolo/uvicorn-gunicorn:python3.7

#LABEL maintainer="Sebastian Ramirez <tiangolo@gmail.com>"

RUN pip install --no-cache-dir fastapi

#COPY ./app /app



WORKDIR /app

# Create the environment:
#COPY environment.yml .
#RUN conda env create -f environment.yml

#RUN pip install uvicorn

#COPY start-reload.sh /
#RUN chmod +x /start-reload.sh

COPY /requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

#COPY ./reasoner/app /app/app
#conda install --yes --file /app/requirements.txt

# Make RUN commands use the new environment:
#SHELL ["conda", "run", "-n", "myenv", "/bin/bash", "-c"]

# Make sure the environment is activated:
#RUN echo "Make sure fastapi is installed:"
#RUN python -c "import fastapi"

# The code to run when container is started:
#COPY run.py .
#ENTRYPOINT ["conda", "run", "--no-capture-output", "-n", "myenv", "python", "/app/run.py"]
