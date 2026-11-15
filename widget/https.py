"""更新请求使用随 App 打包的根证书，不依赖开发机的 Homebrew 路径。"""
import ssl
import urllib.request

import certifi


def open_url(request: urllib.request.Request, *, timeout: float):
    # 显式 cafile 同时保留证书链和主机名校验；证书缺失时正常报错，不能降级为不校验。
    context = ssl.create_default_context(cafile=certifi.where())
    return urllib.request.urlopen(request, timeout=timeout, context=context)
