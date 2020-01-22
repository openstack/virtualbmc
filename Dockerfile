FROM docker.io/fedora:latest

RUN yum -y update && \
	yum install -y git python3 libvirt-python3 python3-pyghmi python3-zmq python3-pbr python3-urllib3 python3-pip golang golang-github-pebbe-zmq4-devel && \
	yum install -y vim && \
	mkdir /root/git && \
	cd /root/git && \
	git clone https://github.com/kubevirt/client-python.git && \
	git clone --recursive https://github.com/kubernetes-client/python.git && \
	git clone https://github.com/colonwq/go-virtualbmc.git
RUN yum install -y pipenv
RUN cd /root/git/python && python setup.py install
ADD . /root/git/virtualbmc
RUN echo "export PYTHONPATH=/root/git/virtualbmc:/root/git/python:/root/git/client-python/" > /root/vbmcd.sh
RUN echo "cd /root/git/virtualbmc" >> /root/vbmcd.sh
RUN echo "python3 virtualbmc/cmd/vbmcd.py --foreground" >> /root/vbmcd.sh

RUN echo "printenv | sort" >> /root/vbmcd.sh
RUN chmod +x /root/vbmcd.sh
RUN mkdir /kubeconfig
VOLUME /kubeconfig
ENV KUBECONFIG /kubeconfig/config
ENV GOPATH /usr/share/gocode
ENV PATH /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/root/git/go-virtualbmc
ENTRYPOINT /root/vbmcd.sh

ENV VIRTUALBMC_CONFIG /kubeconfig/virtualbmc.conf

RUN echo "while [ true ] ; do sleep 20; echo 'going to sleep'; done " > /root/loop.sh
RUN chmod +x /root/loop.sh
RUN yum install -y net-tools ipmitool
#ENTRYPOINT /root/loop.sh 
