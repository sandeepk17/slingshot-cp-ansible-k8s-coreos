FROM debian:jessie
MAINTAINER Christian Simon <simon@swine.de>

RUN apt-get update &&  \
    DEBIAN_FRONTEND=noninteractive apt-get -y install curl build-essential \
    python-pip libffi-dev libgmp-dev python-dev libyaml-dev nano libssl-dev \
    openssh-client && \
    apt-get clean && \
    rm /var/lib/apt/lists/*_*


# get cfssl
ENV CFSSL_VERSION 1.2
ENV CFSSL_HASH eb34ab2179e0b67c29fd55f52422a94fe751527b06a403a79325fed7cf0145bd
ENV CFSSLJSON_HASH 1c9e628c3b86c3f2f8af56415d474c9ed4c8f9246630bd21c3418dbe5bf6401e
RUN curl -s -L -o /usr/local/bin/cfssl     https://pkg.cfssl.org/R${CFSSL_VERSION}/cfssl_linux-amd64 && \
    curl -s -L -o /usr/local/bin/cfssljson https://pkg.cfssl.org/R${CFSSL_VERSION}/cfssljson_linux-amd64 && \
    chmod +x /usr/local/bin/cfssl /usr/local/bin/cfssljson && \
    echo "${CFSSL_HASH}  /usr/local/bin/cfssl" | sha256sum -c && \
    echo "${CFSSLJSON_HASH}  /usr/local/bin/cfssljson" | sha256sum -c

ENV HOME /ansible
RUN sed -i 's/:\/root:/:\/ansible:/g' /etc/passwd

WORKDIR /ansible/code
COPY requirements.txt /ansible/code/
RUN pip install -r requirements.txt

COPY ansible.cfg /ansible/code/

COPY cluster.yaml /ansible/code/
COPY group_vars/coreos.yaml /ansible/code/group_vars/
COPY roles /ansible/code/roles
COPY run.py /ansible/run.py

ENTRYPOINT ["/usr/bin/python", "/ansible/run.py"]

CMD discover
