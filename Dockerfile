# Use the Amazon Linux base image
FROM amazonlinux

# Install necessary packages for building Python
RUN yum update -y && \
    yum install -y gcc openssl-devel bzip2-devel libffi-devel wget tar gzip zlib-devel passwd shadow-utils

# Download and install Python 3.9.13
RUN wget https://www.python.org/ftp/python/3.9.13/Python-3.9.13.tgz && \
    tar -xzf Python-3.9.13.tgz && \
    cd Python-3.9.13 && \
    ./configure --enable-optimizations && \
    make altinstall && \
    cd .. && \
    rm -rf Python-3.9.13* && \
    ln -s /usr/local/bin/python3.9 /usr/local/bin/python

# Install pip
RUN wget https://bootstrap.pypa.io/get-pip.py && \
    python3 get-pip.py && \
    rm get-pip.py
	
# Add user an change working directory and user
RUN groupadd --system app && useradd --system -g app app


# Alternative code that uses the python base image
#FROM python:3.9

WORKDIR /home/app
# Copy whole directory to the container
COPY requirements.txt .

# Install Python library dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Add user an change working directory and user
#RUN addgroup --system app && adduser --system --ingroup app app

RUN chown app:app -R /home/app
USER app

# Copy whole directory to the container
COPY . .

# Expose the port
EXPOSE 8080

# Set entrypoint or default command if needed
#ENTRYPOINT ["python"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]

