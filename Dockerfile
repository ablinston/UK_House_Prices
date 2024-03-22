# Use the Amazon Linux base image
FROM amazonlinux:latest

# Install necessary packages for building Python
RUN yum update -y && \
    yum install -y gcc openssl-devel bzip2-devel libffi-devel wget tar gzip zlib-devel

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

# Copy requirements.txt file
COPY requirements.txt /app/requirements.txt

# Set working directory
WORKDIR /app

# Install Python library dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set entrypoint or default command if needed
ENTRYPOINT ["python"]
CMD ["app.py"]

