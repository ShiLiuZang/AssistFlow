// 管理页面统一为同源 API 请求附加管理员令牌。
(() => {
  const TOKEN_KEY = "minihelp_admin_token";
  const originalFetch = window.fetch.bind(window);
  let tokenPrompt = null;

  async function requestToken(rejectedToken) {
    const current = localStorage.getItem(TOKEN_KEY) || "";
    if (current && current !== rejectedToken) return current;
    if (!tokenPrompt) {
      tokenPrompt = Promise.resolve().then(() => {
        const token = window.prompt("请输入 ADMIN_TOKEN（服务端须配置相同值）");
        if (token) localStorage.setItem(TOKEN_KEY, token);
        return token;
      }).finally(() => { tokenPrompt = null; });
    }
    return tokenPrompt;
  }

  window.fetch = async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : input, location.href);
    if (url.origin !== location.origin || !url.pathname.startsWith("/api/")) {
      return originalFetch(input, init);
    }
    const request = input instanceof Request ? input : new Request(url);
    const template = new Request(request, init);
    const send = (token) => {
      const retry = template.clone();
      const headers = new Headers(retry.headers);
      if (token) headers.set("Authorization", "Bearer " + token);
      return originalFetch(new Request(retry, { headers }));
    };
    const token = localStorage.getItem(TOKEN_KEY) || "";
    const response = await send(token);
    // 只有 401 能靠重新输入令牌解决；503 可能是依赖未就绪或服务端未配置 ADMIN_TOKEN。
    if (response.status !== 401) return response;
    const replacement = await requestToken(token);
    return replacement ? send(replacement) : response;
  };
})();
