FROM ubuntu:18.04
ARG CPYTHON_VERSION=v3.8.11
WORKDIR /

RUN apt update && apt install -y build-essential libssl-dev zlib1g-dev libncurses5-dev libncursesw5-dev \
        libreadline-dev libsqlite3-dev libgdbm-dev libdb5.3-dev libbz2-dev \
        libexpat1-dev liblzma-dev libffi-dev git uuid-dev lsb-core

RUN git clone -b $CPYTHON_VERSION https://github.com/python/cpython
WORKDIR /cpython
RUN ./configure --with-pydebug && make -j -s

WORKDIR /

#Copy test lists
COPY ./test_config_$CPYTHON_VERSION/tests.* /

#workaround - Mystikos does not support Ubunut's default shell dash
RUN ln -sf /bin/bash /bin/sh

#workaround - lsb-core package installation doe snot create /bin/lsb_release symbolic link
RUN ln -sf /usr/bin/lsb_release /bin/lsb_release

#workaround - lsb_release invokes /usr/bin/python3. Ubuntu's default python executable is not PIE, not supported in Mystikos
RUN ln -sf /cpython/python /usr/bin/python3

# Copy Mystikos pdb
COPY ./mpdb.py /cpython/mpdb.py