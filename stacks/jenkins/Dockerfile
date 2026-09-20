FROM jenkins/jenkins:lts
USER root

ARG DV=29.6.2
ARG BASE=https://download.docker.com/linux/static/stable/x86_64

RUN curl -fsSL "$BASE/docker-$DV.tgz" -o /tmp/d.tgz \
 && tar -xzf /tmp/d.tgz -C /tmp docker/docker \
 && mv /tmp/docker/docker /usr/local/bin/docker \
 && rm -rf /tmp/d.tgz /tmp/docker \
 && docker --version

USER jenkins
