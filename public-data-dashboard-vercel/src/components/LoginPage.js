(function () {
  window.PublicDataDashboard = window.PublicDataDashboard || {};

  function LoginPage({
    mode = "login",
    authNotice = "",
    onLogin,
    onSignup,
    onShowSignup,
    onShowLogin,
  }) {
    const isSignup = mode === "signup";
    const page = document.createElement("main");
    page.className = "center-page login-page";

    const shell = document.createElement("section");
    shell.className = "auth-shell";

    const brand = document.createElement("div");
    brand.className = "brand-lockup";
    brand.innerHTML = `
      <div class="brand-mark" aria-hidden="true">D</div>
      <div>
        <p class="eyebrow">Public Data Lab</p>
        <h1>${isSignup ? "회원가입" : "공공데이터 시각화"}</h1>
      </div>
    `;

    const form = document.createElement("form");
    form.className = "form-stack";
    form.noValidate = true;

    const userLabel = document.createElement("label");
    userLabel.textContent = "아이디";
    userLabel.setAttribute("for", "login-id");

    const userInput = document.createElement("input");
    userInput.id = "login-id";
    userInput.type = "text";
    userInput.autocomplete = "username";
    userInput.placeholder = "아이디를 입력하세요";

    const passwordLabel = document.createElement("label");
    passwordLabel.textContent = "비밀번호";
    passwordLabel.setAttribute("for", "login-password");

    const passwordInput = document.createElement("input");
    passwordInput.id = "login-password";
    passwordInput.type = "password";
    passwordInput.autocomplete = "current-password";
    passwordInput.placeholder = "비밀번호를 입력하세요";

    const error = document.createElement("p");
    error.className = authNotice ? "form-error success" : "form-error";
    error.setAttribute("role", "alert");
    error.textContent = authNotice;

    const button = document.createElement("button");
    button.className = "primary-button";
    button.type = "submit";
    button.textContent = isSignup ? "가입하기" : "로그인";

    const switchButton = document.createElement("button");
    switchButton.className = "text-button";
    switchButton.type = "button";
    switchButton.textContent = isSignup
      ? "이미 계정이 있으신가요? 로그인"
      : "회원가입";
    switchButton.addEventListener("click", () => {
      error.textContent = "";

      if (isSignup) {
        onShowLogin();
      } else {
        onShowSignup();
      }
    });

    form.append(
      userLabel,
      userInput,
      passwordLabel,
      passwordInput,
      error,
      button,
      switchButton
    );

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      error.className = "form-error";

      const userId = userInput.value.trim();
      const password = passwordInput.value.trim();

      if (!userId || !password) {
        error.textContent = "아이디와 비밀번호를 모두 입력해 주세요.";
        return;
      }

      const result = isSignup
        ? onSignup(userId, password)
        : onLogin(userId, password);

      error.textContent = result.ok ? result.message || "" : result.message;
    });

    shell.append(brand, form);
    page.appendChild(shell);

    return page;
  }

  window.PublicDataDashboard.LoginPage = LoginPage;
})();
