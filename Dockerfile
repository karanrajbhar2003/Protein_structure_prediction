# Base image: python:3.9-slim (lightweight Linux)
FROM python:3.9-slim as base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    dssp \
    freesasa \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Install conda
RUN wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda.sh && \
    /bin/bash ~/miniconda.sh -b -p /opt/conda && \
    rm ~/miniconda.sh && \
    /opt/conda/bin/conda clean -tipsy && \
    ln -s /opt/conda/etc/profile.d/conda.sh /etc/profile.d/conda.sh && \
    echo ". /opt/conda/etc/profile.d/conda.sh" >> ~/.bashrc && \
    echo "conda activate base" >> ~/.bashrc

# Set the environment
ENV PATH /opt/conda/bin:$PATH

# Install Modeller using conda
ARG MODELLER_KEY
RUN conda config --add channels salilab && \
    conda install modeller -y && \
    echo "MODELLER_KEY='${MODELLER_KEY}'" >> /opt/conda/lib/modeller-10.7/modlib/modeller/config.py

# Install Voronota
# This copies the pre-compiled binaries into the container and adds them to the PATH.
COPY VoroMQA/voronota_1.29.4415 /opt/voronota
ENV PATH=/opt/voronota:$PATH

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Configure a volume for results
# This ensures that generated PDB files are saved on your host machine.
# Example 'docker run' command:
# docker run -v /c/Users/YourUser/MyDocuments/ProteinResults:/app/results my-protein-app
VOLUME /app/results

# Expose port for streamlit app (if you run one)
EXPOSE 8501

# Set the default command to run your main application
# You can override this when you run the container.
CMD ["python", "scripts/run_main_app.py"]
