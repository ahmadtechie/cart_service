FROM python:3.12

# Set environment variables
ENV WorkingDir=/fixam/cart_service
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
RUN mkdir -p ${WorkingDir}
WORKDIR ${WorkingDir}

# install dependencies
RUN pip install --upgrade pip

# copy whole project to your docker home directory.
COPY . ${WorkingDir}

# Install Python dependencies
RUN pip install -r requirements.txt

# port where the Django app runs
ENV DjangoPort=8001

EXPOSE ${DjangoPort}

# Create the entrypoint script
ENV EntryPointFile=${WorkingDir}/entrypoint.sh
ENV APP=cart

RUN echo "#!/bin/bash" > ${EntryPointFile} \
    && echo "sleep 10" >> ${EntryPointFile} \
    && echo "echo 'Initializing Django application...'" >> ${EntryPointFile} \
    && echo "python manage.py makemigrations ${APP}" >> ${EntryPointFile} \
    && echo "python manage.py migrate" >> ${EntryPointFile} \
    && echo "exec gunicorn cart_service.wsgi:application --bind 0.0.0.0:${DjangoPort}" >> ${EntryPointFile}

# Give execute permission to the entrypoint script
RUN chmod +x ${EntryPointFile}

# Define the entrypoint script as the command to run when the container starts
ENTRYPOINT ${EntryPointFile}
