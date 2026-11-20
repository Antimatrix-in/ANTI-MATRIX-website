/**
 * Anti-Matrix — Authentication Controller (Vanilla JS)
 * Handles password visibility toggles, login submission, and the multi-step Email OTP
 * verification & account registration flow.
 */
document.addEventListener('DOMContentLoaded', () => {
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || 
                    document.querySelector('input[name="csrf_token"]')?.value || '';

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
          submitBtn.disabled = false;
          submitBtn.textContent = 'Sign In';
          const passErrSpan = document.getElementById('login-password-err');
          const passInput = document.getElementById('login-password');
          if (passErrSpan && passInput) {
            passInput.classList.add('error');
            passErrSpan.textContent = 'Unable to complete sign in. Please try again.';
            passErrSpan.style.display = 'block';
          }
          return;
        }

        if (res.ok && data && data.status === 'success') {
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
        loginForm.submit();
      }
    });
  }

  // ── 3. Redesigned Step-Based Signup with Email OTP Verification ─────────────
  const signupForm = document.getElementById('signup-form');
  const signupSuccessCard = document.getElementById('signup-success-card');

  if (signupForm) {
    // Steps containers
    const step1Details = document.getElementById('step-1-details');
    const step2Otp = document.getElementById('step-2-otp');
    const step3Password = document.getElementById('step-3-password');

    // Stepper indicators
    const stepInd1 = document.getElementById('step-ind-1');
    const stepInd2 = document.getElementById('step-ind-2');
    const stepInd3 = document.getElementById('step-ind-3');

    // Inputs & buttons
    const nameInput = document.getElementById('signup-name');
    const emailInput = document.getElementById('signup-email');
    const sendOtpBtn = document.getElementById('signup-send-otp-btn');
    const editEmailBtn = document.getElementById('signup-edit-email-btn');
    const sentEmailDisplay = document.getElementById('otp-sent-email-display');

    const otpInput = document.getElementById('signup-otp');
    const verifyOtpBtn = document.getElementById('signup-verify-otp-btn');
    const resendOtpBtn = document.getElementById('signup-resend-otp-btn');
    const cooldownText = document.getElementById('otp-cooldown-text');
    const cooldownTimer = document.getElementById('otp-cooldown-timer');

    const passwordInput = document.getElementById('signup-password');
    const termsCheckbox = document.getElementById('signup-terms');
    const submitBtn = document.getElementById('signup-submit-btn');
    const verificationTokenInput = document.getElementById('signup-verification-token');
    const verifiedEmailPillText = document.getElementById('verified-email-pill-text');

    // Error elements
    const nameErr = document.getElementById('signup-name-err');
    const emailErr = document.getElementById('signup-email-err');
    const otpErr = document.getElementById('signup-otp-err');
    const passwordErr = document.getElementById('signup-password-err');
    const termsErr = document.getElementById('signup-terms-err');
    const globalErr = document.getElementById('signup-global-err');

    let resendInterval = null;
    let resendRemaining = 0;

    // Helper: update stepper UI
    function setStep(stepNumber) {
      if (stepNumber === 1) {
        step1Details.style.display = 'block';
        step2Otp.style.display = 'none';
        step3Password.style.display = 'none';

        updateStepIndicator(stepInd1, true, false);
        updateStepIndicator(stepInd2, false, false);
        updateStepIndicator(stepInd3, false, false);
      } else if (stepNumber === 2) {
        step1Details.style.display = 'none';
        step2Otp.style.display = 'block';
        step3Password.style.display = 'none';

        updateStepIndicator(stepInd1, false, true);
        updateStepIndicator(stepInd2, true, false);
        updateStepIndicator(stepInd3, false, false);

        if (otpInput) {
          otpInput.value = '';
          otpInput.focus();
        }
      } else if (stepNumber === 3) {
        step1Details.style.display = 'none';
        step2Otp.style.display = 'none';
        step3Password.style.display = 'block';

        updateStepIndicator(stepInd1, false, true);
        updateStepIndicator(stepInd2, false, true);
        updateStepIndicator(stepInd3, true, false);

        // Hide OAuth social icons when setting password
        const oauthSection = document.getElementById('signup-oauth-section');
        if (oauthSection) oauthSection.style.display = 'none';

        if (passwordInput) {
          passwordInput.focus();
        }
        validateStep3();
      }
    }

    function updateStepIndicator(elem, isActive, isCompleted) {
      if (!elem) return;
      const numSpan = elem.querySelector('.step-num');
      if (isCompleted) {
        elem.style.color = '#059669';
        elem.style.fontWeight = '600';
        if (numSpan) {
          numSpan.style.background = '#059669';
          numSpan.style.color = '#ffffff';
          numSpan.textContent = '✓';
        }
      } else if (isActive) {
        elem.style.color = '#059669';
        elem.style.fontWeight = '700';
        if (numSpan) {
          numSpan.style.background = '#059669';
          numSpan.style.color = '#ffffff';
        }
      } else {
        elem.style.color = '#94a3b8';
        elem.style.fontWeight = '500';
        if (numSpan) {
          numSpan.style.background = '#e2e8f0';
          numSpan.style.color = '#64748b';
        }
      }
    }

    function startCooldownTimer(seconds = 60) {
      if (resendInterval) clearInterval(resendInterval);
      resendRemaining = seconds;

      if (cooldownText) cooldownText.style.display = 'inline';
      if (resendOtpBtn) resendOtpBtn.style.display = 'none';
      if (cooldownTimer) cooldownTimer.textContent = resendRemaining;

      resendInterval = setInterval(() => {
        resendRemaining -= 1;
        if (cooldownTimer) cooldownTimer.textContent = resendRemaining;

        if (resendRemaining <= 0) {
          clearInterval(resendInterval);
          if (cooldownText) cooldownText.style.display = 'none';
          if (resendOtpBtn) {
            resendOtpBtn.style.display = 'inline';
            resendOtpBtn.disabled = false;
          }
        }
      }, 1000);
    }

    function showGlobalError(msg) {
      if (globalErr) {
        globalErr.textContent = msg;
        globalErr.style.display = 'block';
      }
    }

    function clearGlobalError() {
      if (globalErr) {
        globalErr.textContent = '';
        globalErr.style.display = 'none';
      }
    }

    // ── STEP 1: Send OTP ──────────────────────────────────────────────────
    if (sendOtpBtn) {
      sendOtpBtn.addEventListener('click', async (e) => {
        e.preventDefault();
        clearGlobalError();
        const name = nameInput.value.trim();
        const email = emailInput.value.trim();

        let hasError = false;
        if (!name) {
          nameInput.classList.add('error');
          nameErr.textContent = 'Full name is required';
          nameErr.style.display = 'block';
          hasError = true;
        } else {
          nameInput.classList.remove('error');
          nameErr.textContent = '';
          nameErr.style.display = 'none';
        }

        if (!email) {
          emailInput.classList.add('error');
          emailErr.textContent = 'Email address is required';
          emailErr.style.display = 'block';
          hasError = true;
        } else if (!/^\S+@\S+\.\S+$/.test(email)) {
          emailInput.classList.add('error');
          emailErr.textContent = 'Enter a valid email address';
          emailErr.style.display = 'block';
          hasError = true;
        } else {
          emailInput.classList.remove('error');
          emailErr.textContent = '';
          emailErr.style.display = 'none';
        }

        if (hasError) return;

        sendOtpBtn.disabled = true;
        sendOtpBtn.textContent = 'Sending code…';

        try {
          const res = await fetch('/auth/send-otp', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ name, email })
          });

          const data = await res.json();

          if (res.ok && data.status === 'success') {
            sendOtpBtn.disabled = false;
            sendOtpBtn.textContent = 'Verify Email';

            if (sentEmailDisplay) sentEmailDisplay.textContent = email;
            setStep(2);
            startCooldownTimer(data.resend_in || 60);
          } else {
            sendOtpBtn.disabled = false;
            sendOtpBtn.textContent = 'Verify Email';

            if (data.already_registered) {
              emailInput.classList.add('error');
              emailErr.innerHTML = `${data.message} <a href="/login" class="auth-link" style="margin-left: 4px; font-weight: 600;">Sign in here</a>`;
              emailErr.style.display = 'block';
            } else if (data.errors && data.errors.email) {
              emailInput.classList.add('error');
              emailErr.textContent = data.errors.email;
              emailErr.style.display = 'block';
            } else if (data.errors && data.errors.name) {
              nameInput.classList.add('error');
              nameErr.textContent = data.errors.name;
              nameErr.style.display = 'block';
            } else {
              showGlobalError(data.message || 'Unable to send verification code. Please try again.');
            }
          }
        } catch (err) {
          sendOtpBtn.disabled = false;
          sendOtpBtn.textContent = 'Verify Email';
          showGlobalError('Network error while requesting code. Please try again.');
        }
      });
    }

    // Step 2: Edit email link (returns to Step 1)
    if (editEmailBtn) {
      editEmailBtn.addEventListener('click', (e) => {
        e.preventDefault();
        clearGlobalError();
        if (otpErr) otpErr.style.display = 'none';
        setStep(1);
        if (emailInput) emailInput.focus();
      });
    }

    // Step 2: Resend OTP
    if (resendOtpBtn) {
      resendOtpBtn.addEventListener('click', async (e) => {
        e.preventDefault();
        clearGlobalError();
        const email = emailInput.value.trim();
        if (!email) {
          setStep(1);
          return;
        }

        resendOtpBtn.disabled = true;
        resendOtpBtn.textContent = 'Sending…';

        try {
          const res = await fetch('/auth/resend-otp', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ email })
          });

          const data = await res.json();

          if (res.ok && data.status === 'success') {
            resendOtpBtn.textContent = 'Resend Verification Code';
            startCooldownTimer(data.resend_in || 60);
            if (otpErr) {
              otpErr.style.color = '#059669';
              otpErr.textContent = 'A new verification code has been sent!';
              otpErr.style.display = 'block';
            }
            if (otpInput) {
              otpInput.value = '';
              otpInput.focus();
            }
          } else {
            resendOtpBtn.disabled = false;
            resendOtpBtn.textContent = 'Resend Verification Code';
            if (otpErr) {
              otpErr.style.color = '#dc2626';
              otpErr.textContent = data.message || 'Unable to resend code. Please try again.';
              otpErr.style.display = 'block';
            }
          }
        } catch (err) {
          resendOtpBtn.disabled = false;
          resendOtpBtn.textContent = 'Resend Verification Code';
          if (otpErr) {
            otpErr.style.color = '#dc2626';
            otpErr.textContent = 'Network error. Please try again.';
            otpErr.style.display = 'block';
          }
        }
      });
    }

    // ── STEP 2: Verify OTP ────────────────────────────────────────────────
    if (verifyOtpBtn) {
      verifyOtpBtn.addEventListener('click', async (e) => {
        e.preventDefault();
        await handleVerifyOtp();
      });
    }

    if (otpInput) {
      otpInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          handleVerifyOtp();
        }
      });

      otpInput.addEventListener('input', () => {
        // Strip non-digits
        otpInput.value = otpInput.value.replace(/\D/g, '').slice(0, 6);
        if (otpErr) otpErr.style.display = 'none';
        if (otpInput.value.length === 6) {
          handleVerifyOtp();
        }
      });
    }

    async function handleVerifyOtp() {
      clearGlobalError();
      const email = emailInput.value.trim();
      const otp = otpInput ? otpInput.value.trim() : '';

      if (!otp || otp.length !== 6) {
        if (otpErr) {
          otpErr.style.color = '#dc2626';
          otpErr.textContent = 'Please enter the 6-digit verification code';
          otpErr.style.display = 'block';
        }
        if (otpInput) otpInput.classList.add('error');
        return;
      }

      verifyOtpBtn.disabled = true;
      verifyOtpBtn.textContent = 'Verifying…';

      try {
        const res = await fetch('/auth/verify-otp', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
          },
          body: JSON.stringify({ email, otp })
        });

        const data = await res.json();

        if (res.ok && data.status === 'success') {
          verifyOtpBtn.disabled = false;
          verifyOtpBtn.textContent = 'Verify Code';

          if (verificationTokenInput) {
            verificationTokenInput.value = data.verification_token;
          }
          if (verifiedEmailPillText) {
            verifiedEmailPillText.textContent = `Verified: ${email}`;
          }

          setStep(3);
        } else {
          verifyOtpBtn.disabled = false;
          verifyOtpBtn.textContent = 'Verify Code';

          if (otpInput) otpInput.classList.add('error');
          if (otpErr) {
            otpErr.style.color = '#dc2626';
            otpErr.textContent = data.message || 'Incorrect verification code. Please try again.';
            otpErr.style.display = 'block';
          }

          if (data.lockout) {
            verifyOtpBtn.disabled = true;
            if (otpInput) otpInput.disabled = true;
          }
        }
      } catch (err) {
        verifyOtpBtn.disabled = false;
        verifyOtpBtn.textContent = 'Verify Code';
        if (otpErr) {
          otpErr.style.color = '#dc2626';
          otpErr.textContent = 'Network error while verifying. Please try again.';
          otpErr.style.display = 'block';
        }
      }
    }

    // ── STEP 3: Password Validation & Create Account ──────────────────────
    function validateStep3() {
      const password = passwordInput ? passwordInput.value : '';
      const termsAccepted = termsCheckbox ? termsCheckbox.checked : false;

      const isValid = (password.length >= 8) && termsAccepted;
      if (submitBtn) {
        submitBtn.disabled = !isValid;
      }
      return isValid;
    }

    if (passwordInput) {
      passwordInput.addEventListener('input', () => {
        const password = passwordInput.value;
        if (password.length > 0 && password.length < 8) {
          passwordInput.classList.add('error');
          if (passwordErr) {
            passwordErr.textContent = 'Password must be at least 8 characters';
            passwordErr.style.display = 'block';
          }
        } else {
          passwordInput.classList.remove('error');
          if (passwordErr) {
            passwordErr.textContent = '';
            passwordErr.style.display = 'none';
          }
        }
        validateStep3();
      });
    }

    if (termsCheckbox) {
      termsCheckbox.addEventListener('change', () => {
        if (!termsCheckbox.checked) {
          if (termsErr) {
            termsErr.textContent = 'You must accept the terms to continue';
            termsErr.style.display = 'block';
          }
        } else {
          if (termsErr) {
            termsErr.textContent = '';
            termsErr.style.display = 'none';
          }
        }
        validateStep3();
      });
    }

    // ── Form Submission ───────────────────────────────────────────────────
    signupForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      clearGlobalError();

      const name = nameInput.value.trim();
      const email = emailInput.value.trim();
      const password = passwordInput ? passwordInput.value : '';
      const terms = termsCheckbox ? termsCheckbox.checked : false;
      const verification_token = verificationTokenInput ? verificationTokenInput.value.trim() : '';

      // Validation
      const errors = {};
      if (!name) errors.name = 'Full name is required';
      if (!email) errors.email = 'Email is required';
      if (!password) {
        errors.password = 'Password is required';
      } else if (password.length < 8) {
        errors.password = 'Password must be at least 8 characters';
      }
      if (!terms) errors.terms = 'You must accept the terms to continue';
      if (!verification_token) {
        errors.verification = 'Email verification is required before creating an account';
      }

      if (Object.keys(errors).length > 0) {
        if (errors.password && passwordErr) {
          passwordErr.textContent = errors.password;
          passwordErr.style.display = 'block';
        }
        if (errors.terms && termsErr) {
          termsErr.textContent = errors.terms;
          termsErr.style.display = 'block';
        }
        if (errors.verification) {
          showGlobalError(errors.verification);
        }
        return;
      }

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
          body: JSON.stringify({
            name,
            email,
            password,
            terms,
            verification_token,
            redirect: redirectTarget
          })
        });

        const data = await res.json();

        if (res.ok && data.status === 'success') {
          if (signupSuccessCard) {
            signupForm.style.display = 'none';
            const authHeader = document.getElementById('signup-header');
            const stepper = document.querySelector('.signup-stepper');
            const oauthSection = document.getElementById('signup-oauth-section');
            const authSwitch = document.querySelector('.auth-switch');

            if (authHeader) authHeader.style.display = 'none';
            if (stepper) stepper.style.display = 'none';
            if (oauthSection) oauthSection.style.display = 'none';
            if (authSwitch) authSwitch.style.display = 'none';

            signupSuccessCard.style.display = 'block';
          }
          setTimeout(() => {
            window.location.href = data.redirect || redirectTarget || '/';
          }, 1000);
        } else {
          submitBtn.disabled = false;
          submitBtn.textContent = 'Create Account';
          if (data.errors) {
            if (data.errors.password && passwordErr) {
              passwordErr.textContent = data.errors.password;
              passwordErr.style.display = 'block';
            }
            if (data.errors.terms && termsErr) {
              termsErr.textContent = data.errors.terms;
              termsErr.style.display = 'block';
            }
            if (data.errors.email) {
              showGlobalError(data.errors.email);
            }
            if (data.errors.verification) {
              showGlobalError(data.errors.verification);
            }
          } else {
            showGlobalError(data.message || 'Signup failed. Please try again.');
          }
        }
      } catch (err) {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Create Account';
        showGlobalError('Network error while creating account. Please try again.');
      }
    });

    // Initialize initial state
    setStep(1);
  }
});
