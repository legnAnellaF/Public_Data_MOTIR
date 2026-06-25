(function () {
  window.PublicDataDashboard = window.PublicDataDashboard || {};

  function LoginPage({
    mode = "login",
    errorMessage = "",
    authNotice = "",
    onLogin,
    onSignup,
    onShowLogin,
    onShowSignup,
  }) {
    const isSignupMode = mode === "signup";
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
        <h1>${isSignupMode ? "회원가입" : "공공데이터 시각화"}</h1>
      </div>
    `;

    const modeSwitch = document.createElement("div");
    modeSwitch.className = "auth-mode-switch";

    const loginModeButton = document.createElement("button");
    loginModeButton.type = "button";
    loginModeButton.className = `auth-mode-button ${!isSignupMode ? "active" : ""}`.trim();
    loginModeButton.textContent = "로그인";
    loginModeButton.addEventListener("click", onShowLogin);

    const signupModeButton = document.createElement("button");
    signupModeButton.type = "button";
    signupModeButton.className = `auth-mode-button ${isSignupMode ? "active" : ""}`.trim();
    signupModeButton.textContent = "회원가입";
    signupModeButton.addEventListener("click", onShowSignup);

    modeSwitch.append(loginModeButton, signupModeButton);

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
    passwordInput.autocomplete = isSignupMode ? "new-password" : "current-password";
    passwordInput.placeholder = "비밀번호를 입력하세요";

    const helper = document.createElement("p");
    helper.className = "auth-helper";
    helper.textContent = isSignupMode
      ? "데모용 계정은 이 브라우저의 localStorage에만 저장됩니다."
      : "가입한 데모 계정으로 로그인하면 사용자별 프롬포트 기록을 불러옵니다.";

    const error = document.createElement("p");
    error.className = authNotice ? "form-error success" : "form-error";
    error.setAttribute("role", "alert");
    error.textContent = authNotice || errorMessage;

    const button = document.createElement("button");
    button.className = "primary-button";
    button.type = "submit";
    button.textContent = isSignupMode ? "가입하기" : "로그인";

    form.append(
      userLabel,
      userInput,
      passwordLabel,
      passwordInput,
      helper,
      error,
      button
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

      if (userId.length < 3) {
        error.textContent = "아이디는 3자 이상 입력해 주세요.";
        return;
      }

      if (password.length < 4) {
        error.textContent = "비밀번호는 4자 이상 입력해 주세요.";
        return;
      }

      error.className = "form-error";
      error.textContent = "";

      if (isSignupMode) {
        onSignup(userId, password);
        return;
      }

      onLogin(userId, password);
    });

    shell.append(brand, modeSwitch, form);
    page.appendChild(shell);

    return page;
  }

  window.PublicDataDashboard.LoginPage = LoginPage;
})();
