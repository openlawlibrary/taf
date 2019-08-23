FROM quay.io/pypa/manylinux2010_x86_64
COPY . /taf
RUN yum -y install gcc rpm-build rpm-devel \
  rpmlint make python bash coreutils diffutils \
  patch rpmdevtools wget python-setuptools \
  epel-release python36 python36-devel \
  python36-cryptography python36-setuptools
RUN alias python=/opt/python/cp36-cp36m/bin/python
