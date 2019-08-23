#!/bin/bash
set -e -x

# Install a system packages
yum -y install gcc rpm-build rpm-devel wget glibc swig pcsc-lite-devel

# export PATH=/usr/local/swig/3.0.12/bin/:$PATH
cd /taf
ls -l

# Upgrade pip
/opt/python/cp36-cp36m/bin/python -m pip install --upgrade pip
# Compile wheels
/opt/python/cp36-cp36m/bin/python -m pip install .
/opt/python/cp36-cp36m/bin/python -m pip wheel . -w wheelhouse/

# Bundle external shared libraries into the wheels
for whl in wheelhouse/*.whl; do
    auditwheel repair "$whl" --plat $PLAT -w ./wheelhouse/
done

# Install packages and test
/opt/python/cp36-cp36m/bin/python -m pip install taf --no-index -f ./wheelhouse
