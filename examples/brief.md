# Test failure context

3 unique failure(s).

### 1. test\_total\_includes\_shipping

- Suite: pytest
- Class: tests\.test\_checkout
- Kind: failure
- Source: examples/pytest\.xml

Message: AssertionError: expected 120, got 100

```text
tests/test_checkout.py:18
    assert order.total == 120
E   assert 100 == 120
Environment: API_KEY=[REDACTED]
```

### 2. test\_payment\_service

- Suite: pytest
- Class: tests\.test\_checkout
- Kind: error
- Source: examples/pytest\.xml

Message: ConnectionError: payment service unavailable

```text
tests/test_checkout.py:32
ConnectionError: payment service unavailable
```

### 3. cart &gt; applies a discount

- Suite: src/cart\.test\.ts
- Class: src/cart\.test\.ts
- Kind: failure
- Source: examples/vitest\.xml

Message: expected 90 to be 80

```text
AssertionError: expected 90 to be 80
  at src/cart.test.ts:14:23
```
