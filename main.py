"""在 PyCharm 中直接运行本文件即可启动学习版。"""

import uvicorn


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
