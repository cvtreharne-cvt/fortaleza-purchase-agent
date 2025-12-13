const express = require('express');
const { chromium } = require('playwright');

// Environment
const PORT = process.env.PORT || 3001;
const HEADLESS = process.env.HEADLESS !== 'false';
const CHROME_PATH =
  process.env.CHROME_PATH || process.env.PLAYWRIGHT_CHROMIUM_PATH || '/usr/bin/chromium-browser';

// Timeouts (ms)
const DEFAULT_TIMEOUT = 60000;
const NAVIGATION_TIMEOUT = parseInt(process.env.NAVIGATION_TIMEOUT || `${DEFAULT_TIMEOUT}`, 10);
const SELECTOR_TIMEOUT = 3000;
const SHORT_TIMEOUT = 1000;
const CART_DRAWER_TIMEOUT = 5000;
const ORDER_SUBMISSION_DELAY = 5000;
const TRACKING_REDIRECT_WAIT_MS = 5000;

let browser;
let context;
let page;

const app = express();
app.use(express.json({ limit: '1mb' }));

async function ensurePage() {
  if (page) return page;

  browser = await chromium.launch({
    headless: HEADLESS,
    executablePath: CHROME_PATH,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  });

  context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    userAgent:
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  });

  context.setDefaultTimeout(DEFAULT_TIMEOUT);
  context.setDefaultNavigationTimeout(NAVIGATION_TIMEOUT);

  page = await context.newPage();
  return page;
}

async function resetBrowser() {
  if (browser) {
    await browser.close();
  }
  browser = null;
  context = null;
  page = null;
}

function jsonError(res, statusCode, message, errorType) {
  res.status(statusCode).json({ status: 'error', message, error_type: errorType });
}

async function verifyProductPage(currentPage) {
  const url = currentPage.url();
  if (url.includes('/products/') && !url.includes('/search') && !url.includes('/collections')) {
    const hasPrice = !!(await currentPage.$('.price, [data-price], .product-price'));
    const hasAddToCart = !!(await currentPage.$("button[name='add'], .add-to-cart, [data-add-to-cart]"));
    if (hasPrice || hasAddToCart) return true;
  }
  return false;
}

async function handleAgeVerification(currentPage, dob) {
  const overlaySelectors = [
    '.m-a-v-overlay',
    '.age-verification-overlay',
    '.age-gate',
    '[data-age-verification]',
    '.modal-age-verification',
  ];

  let overlay;
  let matched;
  for (const selector of overlaySelectors) {
    try {
      overlay = await currentPage.waitForSelector(selector, { timeout: 5000 });
      if (overlay) {
        matched = selector;
        break;
      }
    } catch (_) {
      // continue
    }
  }

  if (!overlay) {
    return { status: 'not_found', message: 'No age verification required' };
  }

  // Simple confirmation buttons
  const buttons = [
    "button:has-text('Over 21')",
    "button:has-text('OVER 21')",
    "button:has-text('Yes')",
    "button:has-text('YES')",
    "a:has-text('Enter')",
    "button:has-text('Enter')",
    "button:has-text('I am 21')",
    '.age-verification-yes',
    '[data-age-yes]',
  ];

  for (const selector of buttons) {
    try {
      const button = await currentPage.waitForSelector(selector, { timeout: 2000 });
      if (button) {
        await button.click();
        await currentPage.waitForSelector(matched, { state: 'hidden', timeout: 10000 });
        return { status: 'success', message: 'Age verification completed (button)' };
      }
    } catch (_) {
      // continue
    }
  }

  // Date entry fallback
  const { dob_month, dob_day, dob_year } = dob || {};
  if (!dob_month || !dob_day || !dob_year) {
    return { status: 'error', message: 'Age gate requires DOB but values not provided' };
  }

  const filled = {
    month: await fillField(
      currentPage,
      ["select[name='month']", "input[name='month']", '#age-month', "[placeholder*='Month' i]"],
      dob_month,
    ),
    day: await fillField(
      currentPage,
      ["select[name='day']", "input[name='day']", '#age-day', "[placeholder*='Day' i]"],
      dob_day,
    ),
    year: await fillField(
      currentPage,
      ["select[name='year']", "input[name='year']", '#age-year', "[placeholder*='Year' i]"],
      dob_year,
    ),
  };

  if (!filled.month || !filled.day || !filled.year) {
    const dateInput = await currentPage.$("input[type='date']");
    if (dateInput) {
      const dateStr = `${dob_year}-${dob_month.toString().padStart(2, '0')}-${dob_day
        .toString()
        .padStart(2, '0')}`;
      await dateInput.fill(dateStr);
    }
  }

  const submitSelectors = [
    "button[type='submit']",
    "button:has-text('Enter')",
    "button:has-text('Confirm')",
    "button:has-text('Yes')",
    '.age-verification-submit',
    '[data-age-submit]',
  ];

  for (const selector of submitSelectors) {
    try {
      const submit = await currentPage.waitForSelector(selector, { timeout: 2000 });
      if (submit) {
        await submit.click();
        await currentPage.waitForSelector(matched, { state: 'hidden', timeout: 10000 });
        return { status: 'success', message: 'Age verification completed' };
      }
    } catch (_) {
      // continue
    }
  }

  return { status: 'error', message: 'Could not complete age verification' };
}

async function fillField(currentPage, selectors, value) {
  for (const selector of selectors) {
    try {
      const el = await currentPage.$(selector);
      if (el) {
        const tag = await el.evaluate((node) => node.tagName.toLowerCase());
        if (tag === 'select') {
          await el.selectOption({ value: `${value}` });
        } else {
          await el.fill(`${value}`);
        }
        return true;
      }
    } catch (_) {
      // continue
    }
  }
  return false;
}

async function searchForProduct(currentPage, productName, dob) {
  await currentPage.goto('https://www.bittersandbottles.com', { waitUntil: 'domcontentloaded' });
  const ageResult = await handleAgeVerification(currentPage, dob);
  if (ageResult.status === 'error') return ageResult;

  const searchSelectors = [
    'svg.icon-search',
    '.icon-search',
    '[data-search-toggle]',
    "button:has(svg[class*='search'])",
    "a:has(svg[class*='search'])",
    '.header__search',
    "[aria-label='Search']",
    "button[aria-label='Search']",
  ];

  let searchButton;
  for (const selector of searchSelectors) {
    try {
      searchButton = await currentPage.waitForSelector(selector, { timeout: 2000 });
      if (searchButton) break;
    } catch (_) {
      // continue
    }
  }
  if (!searchButton) return { status: 'error', message: 'Could not find search button/icon' };

  await searchButton.click();
  const searchInput = await currentPage.waitForSelector(
    "input[type='search'], input[name='q'], .search__input, input[placeholder*='Search' i]",
    { timeout: 5000 },
  );
  await searchInput.fill(productName);
  await currentPage.waitForTimeout(1000);

  const slug = productName.toLowerCase().replace(/\\s+/g, '-');
  const suggestionSelectors = [
    `a[href^='/products/'][href*='${slug}']`,
    `.predictive-search a[href^='/products/'][href*='${slug}']`,
    `a[href*='products/${slug}']`,
  ];

  let productLink;
  for (const selector of suggestionSelectors) {
    productLink = await currentPage.$(selector);
    if (productLink) break;
  }

  if (!productLink) {
    await searchInput.press('Enter');
    await currentPage.waitForLoadState('domcontentloaded');
    await currentPage.waitForTimeout(2000);

    const parts = slug.split('-');
    const resultSelectors = [
      `a[href*='${slug}'][href*='products']`,
      `.productitem a[href*='${slug}']`,
      `a[href*='products'][href*='${parts[0]}']`,
      ".product-item a[href*='products']",
      "a.product-link[href*='products']",
    ];
    for (const selector of resultSelectors) {
      try {
        productLink = await currentPage.$(selector);
        if (productLink) break;
      } catch (_) {
        // continue
      }
    }
  }

  if (!productLink) return { status: 'error', message: `Product '${productName}' not found` };

  await productLink.click();
  await currentPage.waitForLoadState('domcontentloaded');

  const isProduct = await verifyProductPage(currentPage);
  if (!isProduct) return { status: 'error', message: 'Search did not reach product page' };

  return { status: 'success', method: 'search', current_url: currentPage.url() };
}

app.get('/health', async (_req, res) => {
  try {
    await ensurePage();
    res.json({ status: 'ok' });
  } catch (e) {
    jsonError(res, 500, e.message);
  }
});

app.post('/reset', async (_req, res) => {
  try {
    await resetBrowser();
    await ensurePage();
    res.json({ status: 'reset' });
  } catch (e) {
    jsonError(res, 500, e.message);
  }
});

app.post('/navigate', async (req, res) => {
  const { direct_link: directLink, product_name: productName, dob } = req.body || {};
  if (!directLink && !productName) {
    return jsonError(res, 400, 'direct_link or product_name required');
  }

  try {
    const currentPage = await ensurePage();

    if (directLink) {
      const response = await currentPage.goto(directLink, { waitUntil: 'domcontentloaded' });
      if (currentPage.url().includes('trk.')) {
        await currentPage.waitForTimeout(TRACKING_REDIRECT_WAIT_MS);
        if (currentPage.url().includes('trk.')) {
          return jsonError(res, 400, `Tracking redirect failed: ${currentPage.url()}`, 'ProtocolError');
        }
      }

      if (response && response.status() === 404) {
        return jsonError(res, 404, `Page not found: ${directLink}`, 'PageNotFound');
      }

      const isProduct = await verifyProductPage(currentPage);
      if (isProduct) {
        return res.json({ status: 'success', method: 'direct_link', current_url: currentPage.url() });
      }
    }

    if (!productName) {
      return jsonError(res, 400, 'Direct link failed and no product_name provided', 'NavigationError');
    }

    const searchResult = await searchForProduct(currentPage, productName, dob);
    if (searchResult.status === 'success') {
      return res.json(searchResult);
    }
    return jsonError(res, 400, searchResult.message || 'Search failed', 'NavigationError');
  } catch (e) {
    return jsonError(res, 500, e.message, 'NavigationError');
  }
});

app.post('/verify-age', async (req, res) => {
  try {
    const currentPage = await ensurePage();
    const result = await handleAgeVerification(currentPage, req.body || {});
    if (result.status === 'error') return jsonError(res, 400, result.message);
    return res.json({ ...result, current_url: currentPage?.url() });
  } catch (e) {
    jsonError(res, 500, e.message);
  }
});

app.post('/login', async (req, res) => {
  const { email, password, dob } = req.body || {};
  if (!email || !password) return jsonError(res, 400, 'email and password required');

  try {
    const currentPage = await ensurePage();
    if (currentPage.url().toLowerCase().includes('/account') && !currentPage.url().toLowerCase().includes('/login')) {
      return res.json({ status: 'success', message: 'Already logged in', current_url: currentPage.url() });
    }

    await currentPage.goto('https://www.bittersandbottles.com/account/login', {
      waitUntil: 'domcontentloaded',
    });

    const ageResult = await handleAgeVerification(currentPage, dob);
    if (ageResult.status === 'error') return jsonError(res, 400, ageResult.message);

    const captchaSelectors = [
      "iframe[src*='recaptcha']",
      '.g-recaptcha',
      '#g-recaptcha',
      "iframe[src*='hcaptcha']",
      '.h-captcha',
      '#h-captcha',
      '.captcha',
      '#captcha',
      "img[alt*='captcha' i]",
      "img[src*='captcha' i]",
    ];
    for (const selector of captchaSelectors) {
      const el = await currentPage.$(selector);
      if (el) return jsonError(res, 400, 'CAPTCHA detected', 'CaptchaRequired');
    }

    const emailSelectors = [
      "input[name='customer[email]']",
      "input[type='email']",
      "input[id*='email' i]",
      "input[placeholder*='email' i]",
    ];
    let emailInput;
    for (const selector of emailSelectors) {
      try {
        emailInput = await currentPage.waitForSelector(selector, { timeout: SELECTOR_TIMEOUT });
        if (emailInput) break;
      } catch (_) {}
    }
    if (!emailInput) return jsonError(res, 400, 'Email field not found');
    await emailInput.fill(email);

    const passwordSelectors = [
      "input[name='customer[password]']",
      "input[type='password']",
      "input[id*='password' i]",
      "input[placeholder*='password' i]",
    ];
    let passwordInput;
    for (const selector of passwordSelectors) {
      try {
        passwordInput = await currentPage.waitForSelector(selector, { timeout: SELECTOR_TIMEOUT });
        if (passwordInput) break;
      } catch (_) {}
    }
    if (!passwordInput) return jsonError(res, 400, 'Password field not found');
    await passwordInput.fill(password);

    const submitSelectors = [
      "button[type='submit']",
      "input[type='submit']",
      "button:has-text('Sign In')",
      "button:has-text('Log In')",
      "button:has-text('Login')",
      '.login-button',
      "[data-action='login']",
    ];
    let submitButton;
    for (const selector of submitSelectors) {
      try {
        submitButton = await currentPage.waitForSelector(selector, { timeout: SELECTOR_TIMEOUT });
        if (submitButton) break;
      } catch (_) {}
    }
    if (!submitButton) return jsonError(res, 400, 'Submit button not found');

    await submitButton.click();
    await currentPage.waitForLoadState('domcontentloaded');

    const twoFaSelectors = [
      "input[name*='code' i]",
      "input[placeholder*='code' i]",
      'text=/verification code/i',
      'text=/authenticator/i',
      'text=/two.factor/i',
      '.two-factor-form',
      '[data-2fa]',
    ];
    for (const selector of twoFaSelectors) {
      try {
        const el = await currentPage.waitForSelector(selector, { timeout: SHORT_TIMEOUT });
        if (el) return jsonError(res, 400, 'Two-factor required', 'TwoFactorRequired');
      } catch (_) {}
    }

    const errorSelectors = [
      '.error-message',
      '.alert-error',
      '.form-error',
      "[role='alert']",
      'text=/incorrect password/i',
      'text=/invalid email/i',
      'text=/login failed/i',
    ];
    for (const selector of errorSelectors) {
      try {
        const el = await currentPage.waitForSelector(selector, { timeout: SHORT_TIMEOUT });
        if (el) {
          const text = (await el.innerText()) || 'Login failed';
          return jsonError(res, 400, text);
        }
      } catch (_) {}
    }

    if (currentPage.url().toLowerCase().includes('/account') && !currentPage.url().toLowerCase().includes('/login')) {
      return res.json({ status: 'success', message: 'Login successful', current_url: currentPage.url() });
    }

    return res.json({ status: 'success', message: 'Login appears successful', current_url: currentPage.url() });
  } catch (e) {
    jsonError(res, 500, e.message);
  }
});

app.post('/add-to-cart', async (req, res) => {
  const { proceed_to_checkout: proceedToCheckout } = req.body || {};
  try {
    const currentPage = await ensurePage();
    const notifySelectors = [
      "button:has-text('NOTIFY ME WHEN AVAILABLE')",
      "button:has-text('NOTIFY ME')",
      "button:has-text('Notify me')",
    ];
    for (const selector of notifySelectors) {
      try {
        const el = await currentPage.waitForSelector(selector, { timeout: SHORT_TIMEOUT });
        if (el) return jsonError(res, 400, 'Product sold out - notify me button present', 'ProductSoldOut');
      } catch (_) {}
    }

    const addSelectors = [
      "button:has-text('ADD TO CART')",
      "button:has-text('Add to Cart')",
      "button[name='add']",
      "button[data-add-to-cart]",
      '.product-form__submit',
      "[data-action='add-to-cart']",
      "input[type='submit'][value*='Add']",
    ];
    let addButton;
    for (const selector of addSelectors) {
      try {
        const btn = await currentPage.waitForSelector(selector, { timeout: SELECTOR_TIMEOUT });
        if (btn && !(await btn.isDisabled())) {
          addButton = btn;
          break;
        }
      } catch (_) {}
    }
    if (!addButton) return jsonError(res, 400, 'Add to cart button missing/disabled', 'ProductSoldOut');

    await addButton.click();
    try {
      await currentPage.waitForSelector('text=/Added to.*cart/i', { timeout: CART_DRAWER_TIMEOUT });
    } catch (_) {
      // continue
    }

    const successIndicators = ['text=/Added to.*cart/i', 'text=/item.*added/i', '.cart-item', '[data-cart-item]'];
    let added = false;
    for (const selector of successIndicators) {
      try {
        const el = await currentPage.waitForSelector(selector, { timeout: SHORT_TIMEOUT });
        if (el) {
          added = true;
          break;
        }
      } catch (_) {}
    }
    if (!added) return jsonError(res, 400, 'Could not verify cart add');

    if (proceedToCheckout) {
      const checkoutSelectors = [
        "button:has-text('CHECKOUT')",
        "a:has-text('CHECKOUT')",
        "[data-checkout]",
        '.cart-drawer__checkout',
        "button[name='checkout']",
      ];
      let checkoutButton;
      for (const selector of checkoutSelectors) {
        try {
          checkoutButton = await currentPage.waitForSelector(selector, { timeout: SELECTOR_TIMEOUT });
          if (checkoutButton) break;
        } catch (_) {}
      }
      if (!checkoutButton) return jsonError(res, 400, 'Checkout button not found');
      await checkoutButton.click();
      await currentPage.waitForLoadState('domcontentloaded');
      return res.json({
        status: 'success',
        message: 'Product added and proceeded to checkout',
        current_url: currentPage.url(),
      });
    }

    return res.json({ status: 'success', message: 'Product added to cart', current_url: currentPage.url() });
  } catch (e) {
    jsonError(res, 500, e.message);
  }
});

app.post('/checkout', async (req, res) => {
  const {
    submit_order: submitOrder,
    payment,
    pickup_preference: pickupPreference,
  } = req.body || {};
  const paymentInfo = payment || {};

  try {
    const currentPage = await ensurePage();
    if (!currentPage.url().toLowerCase().includes('checkout')) {
      return jsonError(res, 400, `Not on checkout page (${currentPage.url()})`);
    }

    await currentPage.waitForLoadState('domcontentloaded');

    await verifyPickupSelected(currentPage);
    const pickupLocation = await detectPickupLocation(currentPage);

    await fillPayment(currentPage, paymentInfo);

    const orderSummary = await getOrderSummary(currentPage, pickupLocation);

    if (submitOrder) {
      const submitSelectors = [
        "button:has-text('Pay now')",
        "button[type='submit']:has-text('Pay')",
        "button:has-text('Complete order')",
        "button:has-text('Place order')",
        "button[type='submit']",
        '#submit-button',
      ];
      let submitButton;
      for (const selector of submitSelectors) {
        try {
          submitButton = await currentPage.waitForSelector(selector, { timeout: SELECTOR_TIMEOUT });
          if (submitButton) break;
        } catch (_) {}
      }
      if (!submitButton) return jsonError(res, 400, "'Pay now' button not found");

      await submitButton.click();
      await currentPage.waitForTimeout(ORDER_SUBMISSION_DELAY);

      const threeDs = await check3DS(currentPage);
      if (threeDs) return jsonError(res, 400, '3D Secure verification required', 'ThreeDSecureRequired');

      const paymentError = await checkPaymentError(currentPage);
      if (paymentError) return jsonError(res, 400, `Payment failed: ${paymentError}`);

      const success =
        currentPage.url().toLowerCase().includes('thank') ||
        currentPage.url().toLowerCase().includes('confirmation') ||
        currentPage.url().toLowerCase().includes('order');

      return res.json({
        status: 'success',
        message: success ? 'Order submitted successfully' : 'Order submission unclear',
        order_summary: orderSummary,
        confirmation_url: success ? currentPage.url() : undefined,
        order_placed: success,
        current_url: currentPage.url(),
      });
    }

    return res.json({
      status: 'success',
      message: 'Checkout completed (no submit)',
      order_summary: orderSummary,
      current_url: currentPage.url(),
    });
  } catch (e) {
    jsonError(res, 500, e.message);
  }
});

async function verifyPickupSelected(currentPage) {
  const pickupSelectors = [
    "input[type='radio'][value*='pick']:checked",
    "input[type='radio'][id*='pickup']:checked",
    "input[type='radio']:checked + label:has-text('Pick')",
  ];

  for (const selector of pickupSelectors) {
    const el = await currentPage.$(selector);
    if (el) return;
  }

  const clickSelectors = [
    "input[type='radio'][value*='pick']",
    "label:has-text('Pick-up')",
    "label:has-text('Pick up')",
  ];
  for (const selector of clickSelectors) {
    try {
      const el = await currentPage.waitForSelector(selector, { timeout: SELECTOR_TIMEOUT });
      if (el) {
        await el.click();
        await currentPage.waitForTimeout(1000);
        return;
      }
    } catch (_) {}
  }
}

async function detectPickupLocation(currentPage) {
  const selectors = [
    'text=/South San Francisco.*240 Grand/i',
    'text=/San Francisco.*Fell Street/i',
    'text=/South San Francisco/i',
    'text=/1275 Fell Street/i',
    'text=/240 Grand Ave/i',
  ];

  for (const selector of selectors) {
    try {
      const el = await currentPage.waitForSelector(selector, { timeout: 2000 });
      if (el) {
        const text = await el.innerText();
        return text.split('\\n')[0].trim().slice(0, 50);
      }
    } catch (_) {}
  }
  return 'unknown';
}

async function fillPayment(currentPage, paymentInfo) {
  const {
    cc_number: ccNumber,
    cc_exp_month: ccExpMonth,
    cc_exp_year: ccExpYear,
    cc_cvv: ccCvv,
    billing_name: billingName,
  } = paymentInfo;

  const paymentSection = await currentPage.$('text=/Payment/i');
  if (paymentSection) {
    await paymentSection.scrollIntoViewIfNeeded();
    await currentPage.waitForTimeout(1000);
  }

  const cardIframe = await currentPage.waitForSelector(
    "iframe[title*='Field container for: Card number' i], iframe[name*='number' i]",
    { timeout: 5000 },
  );
  if (!cardIframe) throw new Error('Card number iframe not found');
  const cardFrame = await cardIframe.contentFrame();
  const cardInput = await cardFrame.waitForSelector('input', { timeout: 5000 });
  await cardInput.click({ force: true });
  await currentPage.waitForTimeout(200);
  await cardInput.type(ccNumber, { delay: 30 });
  await cardInput.press('Tab');
  await currentPage.waitForTimeout(500);

  const expValue = `${ccExpMonth.toString().padStart(2, '0')}${ccExpYear.toString().slice(-2)}`;
  await currentPage.keyboard.type(expValue, { delay: 30 });
  await currentPage.keyboard.press('Tab');
  await currentPage.waitForTimeout(500);

  await currentPage.keyboard.type(ccCvv, { delay: 30 });
  await currentPage.keyboard.press('Tab');
  await currentPage.waitForTimeout(500);

  await currentPage.keyboard.type(billingName, { delay: 30 });
}

async function getOrderSummary(currentPage, pickupLocation) {
  const summary = {
    subtotal: 'unknown',
    tax: 'unknown',
    total: 'unknown',
    pickup_location: pickupLocation || 'unknown',
    quantity: 'unknown',
  };

  try {
    const subtotalElem = await currentPage.$('text=/^Subtotal$/i');
    if (subtotalElem) {
      const grandparent = await subtotalElem.evaluateHandle((el) => el.parentElement.parentElement);
      const text = await grandparent.innerText();
      if (text.includes('$')) summary.subtotal = `$${text.split('$')[1].trim().split(/\\s+/)[0]}`;
    }
  } catch (_) {}

  try {
    const taxElem = await currentPage.$('text=/^Estimated taxes$/i');
    if (taxElem) {
      const parent4 = await taxElem.evaluateHandle(
        (el) => el.parentElement?.parentElement?.parentElement?.parentElement,
      );
      const text = await parent4.innerText();
      if (text.includes('$')) summary.tax = `$${text.split('$')[1].trim().split(/\\s+/)[0]}`;
    }
  } catch (_) {}

  try {
    const totalElem = await currentPage.$('text=/^Total$/i');
    if (totalElem) {
      const grandparent = await totalElem.evaluateHandle((el) => el.parentElement.parentElement);
      const text = await grandparent.innerText();
      if (text.includes('$')) summary.total = `$${text.split('$')[1].trim().split(/\\s+/)[0]}`;
    }
  } catch (_) {}

  // Quantity: sum item quantities in order summary
  try {
    // Prefer Shopify checkout line_items if available
    // Note: This doesn't work on bittersandbottles.com but kept as an opportunistic
    // first check - it's fast and might work on other Shopify stores
    const qtyShopify = await currentPage.evaluate(() => {
      try {
        const items = window.Shopify?.checkout?.line_items || [];
        return items.reduce((sum, item) => sum + (item.quantity || 0), 0);
      } catch (e) {
        return null;
      }
    });
    if (qtyShopify && qtyShopify > 0) {
      summary.quantity = qtyShopify;
    }

    // Try to find quantity by looking for "Quantity" label followed by aria-hidden span
    // This is the pattern used in Shopify checkout pages
    if (!summary.quantity || summary.quantity === 'unknown') {
      const qtyFromLabel = await currentPage.evaluate(() => {
        try {
          // Find all spans that contain "Quantity" text
          const allSpans = Array.from(document.querySelectorAll('span'));
          const qtyLabel = allSpans.find(span => span.textContent.trim().toLowerCase() === 'quantity');

          if (qtyLabel) {
            // Look for next sibling with aria-hidden="true"
            let nextSibling = qtyLabel.nextElementSibling;
            if (nextSibling && nextSibling.tagName === 'SPAN' && nextSibling.getAttribute('aria-hidden') === 'true') {
              const qtyText = nextSibling.textContent.trim();
              const match = qtyText.match(/\d+/);
              return match ? parseInt(match[0], 10) : null;
            }
          }
          return null;
        } catch (e) {
          return null;
        }
      });

      if (qtyFromLabel && qtyFromLabel > 0) {
        summary.quantity = qtyFromLabel;
      }
    }

    let qtyTotal = 0;
    const qtyNodes = await currentPage.$$(
      '.product__quantity, .order-summary__quantity, [data-checkout-line-item] .quantity, .product-table__quantity, '
        + 'select[data-cartitem-quantity], [data-quantity], [data-cart-item-quantity], '
        + "select[aria-label='Quantity'], select[id^='quantity'], select[name*='quantity'], "
        + '.product-thumbnail__quantity, span.product-thumbnail__quantity, span[class*="thumbnail__quantity"], '
        + "span[data-order-summary-section='line-item-quantity']",
    );
    for (const node of qtyNodes) {
      const tag = ((await node.evaluate((el) => el.tagName)) || '').toLowerCase();
      if (tag === 'select') {
        const val = await node.getAttribute('value');
        if (val && /^\d+$/.test(val)) {
          qtyTotal += parseInt(val, 10);
        } else {
          const opt = await node.$('option:checked');
          if (opt) {
            const optText = ((await opt.innerText()) || '').trim();
            const digitsOpt = optText.replace(/[^0-9]/g, '');
            if (digitsOpt) qtyTotal += parseInt(digitsOpt, 10);
          }
        }
      } else {
        const text = ((await node.innerText()) || '').trim();
        const digits = text.replace(/[^0-9]/g, '');
        if (digits) qtyTotal += parseInt(digits, 10);
      }
    }
    if (qtyTotal > 0) summary.quantity = qtyTotal;
  } catch (_) {}

  return summary;
}

async function check3DS(currentPage) {
  const selectors = [
    "iframe[name*='3d']",
    "iframe[name*='secure']",
    'text=/3d secure/i',
    'text=/verify/i',
    '#challenge-iframe',
  ];
  for (const selector of selectors) {
    try {
      const el = await currentPage.waitForSelector(selector, { timeout: SHORT_TIMEOUT });
      if (el) return true;
    } catch (_) {}
  }
  return false;
}

async function checkPaymentError(currentPage) {
  const selectors = [
    '.error-message',
    '.payment-error',
    "[role='alert']",
    'text=/payment.*failed/i',
    'text=/card.*declined/i',
    'text=/error/i',
  ];
  for (const selector of selectors) {
    try {
      const el = await currentPage.waitForSelector(selector, { timeout: SHORT_TIMEOUT });
      if (el) return (await el.innerText()) || 'Payment error';
    } catch (_) {}
  }
  return null;
}

process.on('SIGINT', async () => {
  await resetBrowser();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  await resetBrowser();
  process.exit(0);
});

app.listen(PORT, () => {
  console.log(`Browser worker listening on port ${PORT} (headless=${HEADLESS}, chrome=${CHROME_PATH})`);
});
