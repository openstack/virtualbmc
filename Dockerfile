FROM docker.io/fedora:latest

RUN yum -y update && \
	yum install -y git python3 libvirt-python3 python3-pyghmi python3-zmq python3-pbr && \
	mkdir /root/git && \
	cd /root/git && \
	git clone https://github.com/colonwq/virtualbmc.git
RUN echo "export PYTHONPATH=/root/git/virtualbmc" > /root/vbmcd.sh
RUN echo "cd /root/git/virtualbmc" >> /root/vbmcd.sh
RUN echo "python3 virtualbmc/cmd/vbmcd.py --foreground" >> /root/vbmcd.sh

RUN echo "printenv | sort" >> /root/vbmcd.sh
RUN chmod +x /root/vbmcd.sh

#RUN echo "while [ true ] ; do sleep 5 ; done" > /root/loop.sh
#RUN chmod +x /root/loop.sh

ENTRYPOINT /root/vbmcd.sh
#ENTRYPOINT /root/loop.sh
