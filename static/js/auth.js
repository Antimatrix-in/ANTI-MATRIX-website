/**
 * Anti-Matrix — Authentication Controller (Vanilla JS)
 * Handles password visibility toggles and asynchronous form submission for Login & Signup.
 */
document.addEventListener('DOMContentLoaded', () => {
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';

  // ── 1. Password Visibility Toggle ───────────────────────────────────────
  const toggleButtons = document.querySelectorAll('.password-toggle');
  toggleButtons.forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const targetId = btn.getAttribute('data-target');
      const input = document.getElementById(targetId);
      const iconEye = btn.querySelector('.icon-eye');
      const iconEyeOff = btn.querySelector('.icon-eye-off');

      if (input) {
        const isPassword = input.type === 'password';
        input.type = isPassword ? 'text' : 'password';
        btn.setAttribute('aria-label', isPassword ? 'Hide password' : 'Show password');
        if (iconEye && iconEyeOff) {
          iconEye.style.display = isPassword ? 'none' : 'inline-block';
          iconEyeOff.style.display = isPassword ? 'inline-block' : 'none';
        }
      }
    });
  });

  // ── 2. Login Form Submission ────────────────────────────────────────────
  const loginForm = document.getElementById('login-form');
  const loginSuccessCard = document.getElementById('login-success-card');

  if (loginForm) {
    const emailInput = document.getElementById('login-email');
    const passwordInput = document.getElementById('login-password');
    const rememberCheckbox = document.getElementById('login-remember');
    const submitBtn = document.getElementById('login-submit-btn');

    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = emailInput.value.trim();
      const password = passwordInput.value;
      const remember = rememberCheckbox ? rememberCheckbox.checked : false;

      // Client validation
      const errors = {};
      if (!email) {
        errors.email = 'Email or Employee ID is required';
      } else if (!/^\S+@\S+\.\S+$/.test(email) && !/^AM[A-Za-z0-9]+$/i.test(email)) {
        errors.email = 'Enter a valid email or Employee ID (e.g. AM4827)';
      }
      if (!password) {
        errors.password = 'Password is required';
      } else if (password.length < 6) {
        errors.password = 'Password must be at least 6 characters';
      }

      // Render errors
      ['email', 'password'].forEach((field) => {
        const input = document.getElementById(`login-${field}`);
        const errSpan = document.getElementById(`login-${field}-err`);
        if (errors[field]) {
          if (input) input.classList.add('error');
          if (errSpan) {
            errSpan.textContent = errors[field];
            errSpan.style.display = 'block';
          }
        } else {
          if (input) input.classList.remove('error');
          if (errSpan) {
            errSpan.textContent = '';
            errSpan.style.display = 'none';
          }
        }
      });

      if (Object.keys(errors).length > 0) return;

      submitBtn.disabled = true;
      submitBtn.textContent = 'Signing in…';

      const redirectInput = loginForm.querySelector('input[name="redirect"]');
      const urlParams = new URLSearchParams(window.location.search);
      const redirectTarget = redirectInput ? redirectInput.value : (urlParams.get('next') || urlParams.get('redirect') || '');

      try {
        const res = await fetch('/login', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
          },
          body: JSON.stringify({ email, password, remember, redirect: redirectTarget })
        });

        let data = null;
        try {
          data = await res.json();
        } catch (jsonErr) {
          // If response is not valid JSON (e.g. server error HTML), do NOT submit the form and navigate to 404
          submitBtn.disabled = false;
          submitBtn.textContent = 'Sign In';
          const passErrSpan = document.getElementById('login-password-err');
          const passInput = document.getElementById('login-password');
          if (passErrSpan && passInput) {
            passInput.classList.add('error');
            passErrSpan.textContent = 'Unable to complete sign in. Please try again.';
            passErrSpan.style.display = 'block';
          } else {
            alert('Unable to complete sign in. Please try again.');
          }
          return;
        }

        if (res.ok && data && data.status === 'success') {
          // Display success state matching Login.jsx
          if (loginSuccessCard) {
            loginForm.style.display = 'none';
            const authHeader = document.getElementById('auth-header');
            if (authHeader) authHeader.style.display = 'none';
            loginSuccessCard.style.display = 'block';
          }
          setTimeout(() => {
            window.location.href = data.redirect || redirectTarget || '/';
          }, 900);
        } else {
          submitBtn.disabled = false;
          submitBtn.textContent = 'Sign In';
          if (data && data.errors) {
            Object.keys(data.errors).forEach((field) => {
              const input = document.getElementById(`login-${field}`);
              const errSpan = document.getElementById(`login-${field}-err`);
              if (input) input.classList.add('error');
              if (errSpan) {
                errSpan.textContent = data.errors[field];
                errSpan.style.display = 'block';
              }
            });
          } else {
            const passErrSpan = document.getElementById('login-password-err');
            const passInput = document.getElementById('login-password');
            const msg = (data && data.message) || 'Invalid email or password';
            if (passErrSpan && passInput) {
              passInput.classList.add('error');
              passErrSpan.textContent = msg;
              passErrSpan.style.display = 'block';
            } else {
              alert(msg);
            }
          }
        }
      } catch (err) {
        // Only if network fetch itself failed before receiving response
        loginForm.submit();
      }
    });
  }

  // ── 3. Signup Form Submission ───────────────────────────────────────────
  const signupForm = document.getElementById('signup-form');
  const signupSuccessCard = document.getElementById('signup-success-card');

  if (signupForm) {
    const nameInput = document.getElementById('signup-name');
    const emailInput = document.getElementById('signup-email');
    const passwordInput = document.getElementById('signup-password');
    const confirmInput = document.getElementById('signup-confirm');
    const termsCheckbox = document.getElementById('signup-terms');
    const submitBtn = document.getElementById('signup-submit-btn');

    signupForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const name = nameInput.value.trim();
      const email = emailInput.value.trim();
      const password = passwordInput.value;
      const confirm = confirmInput.value;
      const terms = termsCheckbox ? termsCheckbox.checked : false;

      // Validation
      const errors = {};
      if (!name) errors.name = 'Full name is required';
      if (!email) {
        errors.email = 'Email is required';
      } else if (!/^\S+@\S+\.\S+$/.test(email)) {
        errors.email = 'Enter a valid email address';
      }
      if (!password) {
        errors.password = 'Password is required';
      } else if (password.length < 8) {
        errors.password = 'Password must be at least 8 characters';
      }
      if (!confirm) {
        errors.confirm = 'Please confirm your password';
      } else if (confirm !== password) {
        errors.confirm = 'Passwords do not match';
      }
      if (!terms) errors.terms = 'You must accept the terms to continue';

      // Render errors
      ['name', 'email', 'password', 'confirm', 'terms'].forEach((field) => {
        const input = document.getElementById(`signup-${field}`);
        const errSpan = document.getElementById(`signup-${field}-err`);
        if (errors[field]) {
          if (input) input.classList.add('error');
          if (errSpan) {
            errSpan.textContent = errors[field];
            errSpan.style.display = 'block';
          }
        } else {
          if (input) input.classList.remove('error');
          if (errSpan) {
            errSpan.textContent = '';
            errSpan.style.display = 'none';
          }
        }
      });

      if (Object.keys(errors).length > 0) return;

      submitBtn.disabled = true;
      submitBtn.textContent = 'Creating account…';

      const redirectInput = signupForm.querySelector('input[name="redirect"]');
      const urlParams = new URLSearchParams(window.location.search);
      const redirectTarget = redirectInput ? redirectInput.value : (urlParams.get('next') || urlParams.get('redirect') || '');

      try {
        const res = await fetch('/signup', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
          },
          body: JSON.stringify({ name, email, password, confirm, terms, redirect: redirectTarget })
        });

        const data = await res.json();

        if (res.ok && data.status === 'success') {
          if (signupSuccessCard) {
            signupForm.style.display = 'none';
            const authHeader = document.getElementById('signup-header');
            const benefitsBox = document.getElementById('signup-benefits');
            if (authHeader) authHeader.style.display = 'none';
            if (benefitsBox) benefitsBox.style.display = 'none';
            signupSuccessCard.style.display = 'block';
          }
          setTimeout(() => {
            window.location.href = data.redirect || redirectTarget || '/';
          }, 1200);
        } else {
          submitBtn.disabled = false;
          submitBtn.textContent = 'Create Account';
          if (data.errors) {
            Object.keys(data.errors).forEach((field) => {
              const input = document.getElementById(`signup-${field}`);
              const errSpan = document.getElementById(`signup-${field}-err`);
              if (input) input.classList.add('error');
              if (errSpan) {
                errSpan.textContent = data.errors[field];
                errSpan.style.display = 'block';
              }
            });
          } else {
            alert(data.message || 'Signup failed. Please try again.');
          }
        }
      } catch (err) {
        signupForm.submit();
      }
    });
  }
});
