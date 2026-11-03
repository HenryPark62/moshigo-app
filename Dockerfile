# 배포용 실행 설정 (Render 등 Docker를 받는 곳). 포트는 배포처가 주는 PORT를 쓴다
FROM python:3.13-slim

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1 PORT=8501
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
# 링크 미리보기(카카오톡 등)에 'Streamlit' 대신 모시고 제목과 그림이 나오게
COPY --chown=user scripts/patch_index.py scripts/
RUN python scripts/patch_index.py

COPY --chown=user . .

EXPOSE 8501
CMD streamlit run streamlit_app.py --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true --server.enableStaticServing=true
