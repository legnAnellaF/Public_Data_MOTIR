(function () {
  window.PublicDataDashboard = window.PublicDataDashboard || {};

  function LoginPage({ onLogin }) {
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
        <h1>공공데이터 시각화</h1>
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
    error.className = "form-error";
    error.setAttribute("role", "alert");

    const button = document.createElement("button");
    button.className = "primary-button";
    button.type = "submit";
    button.textContent = "로그인";

    form.append(userLabel, userInput, passwordLabel, passwordInput, error, button);

    form.addEventListener("submit", (event) => {
      event.preventDefault();

      const userId = userInput.value.trim();
      const password = passwordInput.value.trim();

      // 현재는 임시 로그인이며 추후 백엔드 인증 API로 대체 가능.
      if (userId && password) {
        error.textContent = "";
        onLogin();
        return;
      }

      error.textContent = "아이디와 비밀번호를 모두 입력해 주세요.";
    });

    shell.append(brand, form);
    page.appendChild(shell);

    return page;
  }

  window.PublicDataDashboard.LoginPage = LoginPage;
})();
