import os
import requests
import zipfile
import io

# URL of the repository zip file
repo_url = 'https://github.com/openlawlibrary/taf/archive/refs/heads/master.zip'

# Directory where you want to extract the repository
clone_dir = '/'

# Download the repository zip file
response = requests.get(repo_url)
if response.status_code == 200:
    print('Repository zip file downloaded successfully')
else:
    raise Exception(f'Failed to download repository: {response.status_code}')

# Extract the zip file
with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
    zip_ref.extractall(clone_dir)

print(f'Repository successfully extracted to {clone_dir}')

# Rename the extracted directory to the desired name
extracted_dir = os.path.join(clone_dir, 'taf-main')
if os.path.exists(extracted_dir):
    for item in os.listdir(extracted_dir):
        s = os.path.join(extracted_dir, item)
        d = os.path.join(clone_dir, item)
        os.rename(s, d)
    os.rmdir(extracted_dir)
