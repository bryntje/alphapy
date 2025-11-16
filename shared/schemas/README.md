# Innersync Shared Schemas

This folder centralises the domain models that are consumed by the Alphapy API, the Innersync App dashboard and any future services (Core API, worker jobs, etc.).

Two flavours are offered:

- `schemas/typescript`: TypeScript + Zod definitions that can be imported inside web apps or Node services.
- `schemas/python`: Pydantic models that ensure the same contracts on the Python side.

## TypeScript usage

```ts
// schemas/typescript/index.ts
import { UserSchema, type User } from "../../schemas/typescript";

function handleUser(payload: unknown): User {
  const parsed = UserSchema.parse(payload); // throws if invalid
  return parsed;
}
```

The file exports both the Zod schemas (`UserSchema`, `ProfileSchema`, …) and the inferred TypeScript types (`User`, `Profile`, …). The schemas can be published as their own package later (`@innersync/schemas`) once tooling is in place.

## Python usage

```python
from schemas.python import User, Reflection

def handle_user(payload: dict) -> User:
    return User.model_validate(payload)
```

All models inherit from `pydantic.BaseModel`, so `.model_validate` and `.model_dump` can be used to validate or serialise payloads.

## Next steps

- Publish the TypeScript folder as an npm package and the Python folder as a poetry/pyproject package.
- Replace hardcoded DTOs in Alphapy, Alphamind, and Innersync App with imports from this folder (Git submodule or package).
- Extend the schemas as new domains (habits, sessions, metrics) become stable.
