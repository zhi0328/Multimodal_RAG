import os

from dotenv import load_dotenv

load_dotenv(override=True)

GLM_API_KEY = os.getenv('GLM_API_KEY')
SILICONFLOW_API_KEY = os.getenv('SILICONFLOW_API_KEY')
MINIMAX_API_KEY = os.getenv('MINIMAX_API_KEY')
ALIBABA_API_KEY = os.getenv('ALIBABA_API_KEY')
K2_API_KEY = os.getenv('K2_API_KEY')
MIMO_API_KEY = os.getenv('MIMO_API_KEY')

K2_BASE_URL = os.getenv('K2_BASE_URL')
ALIBABA_BASE_URL = os.getenv('ALIBABA_BASE_URL')
MINIMAX_BASE_URL = os.getenv('MINIMAX_BASE_URL')
GLM_BASE_URL = os.getenv('GLM_BASE_URL')
SILICONFLOW_BASE_URL = os.getenv('SILICONFLOW_BASE_URL')
MIMO_BASE_URL = os.getenv('MIMO_BASE_URL')

LOCAL_BASE_URL = os.getenv('LOCAL_BASE_URL')

REDIS_URL = os.getenv('REDIS_URL')