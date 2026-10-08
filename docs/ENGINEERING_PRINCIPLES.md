# Engineering principles

The working rules for this codebase, distilled from the sources below. Every design choice in
[DECISIONS.md](DECISIONS.md) is checked against this page.

## Sources

| Source | Read |
| --- | --- |
| refactoring.guru: refactoring (clean code, technical debt, when and how to refactor) | In full |
| refactoring.guru: all 23 code-smell pages | In full |
| refactoring.guru: the six technique categories (all 66 techniques, problem and solution) | Category pages; single technique pages are opened when a decision needs one |
| refactoring.guru: design patterns overview, classification, criticism, catalog; Strategy, Factory Method, Template Method, Facade, Adapter, Singleton | In full |
| Stack Overflow blog: Best practices for REST API design | In full |
| Microsoft Azure Architecture Center: Web API design best practices | In full |
| Medium (S. A. Rahman): Mastering REST API design | **Not read.** Medium refused automated access from this network (connection refused, then HTTP 403). The summary supplied with the brief was used instead; its points are all covered by the other two guides. |

## Clean code, as the test for every file

1. Obvious to another programmer: domain names (`Measurement`, `GeoDataset`), no unexplained numbers.
2. No duplication.
3. The fewest classes and moving parts that do the job. Code is a liability.
4. All tests pass, all the time.

## How we change code

- Small steps, tests green after each one.
- Refactoring commits and feature commits are separate; a refactor adds no behaviour.
- Rule of three: tolerate the second copy, refactor on the third.
- Tests target behaviour (API responses, measured values), not private functions, so refactoring does not break them.

## Smells and how this project avoids them

| Smell | Rule here |
| --- | --- |
| Long Method, Large Class | One job per function. The upload pipeline is a short list of named steps, not one function. |
| Primitive Obsession, Data Clumps | A measurement is one `Measurement` object (value, unit, method, CRS, status, reason), never loose strings and floats. Statuses and formats are enums. |
| Long Parameter List | Pass the object (`GeoDataset`, `Measurement`), not five of its fields. |
| Switch Statements | Geometry type and file format are looked up in a table. No `if/elif` chain on type. Adding a format is one new reader and one table entry. |
| Divergent Change, Shotgun Surgery | Layers change for one reason each: HTTP in `api`, file parsing in `readers`, maths in `geometry`, SQL in `repositories`. |
| Feature Envy, Inappropriate Intimacy, Message Chains | Routers never touch GeoPandas or SQL. Only readers see a GeoDataFrame; they hand back plain objects. |
| Middle Man, Lazy Class | No class that only forwards calls. A plain function is preferred over a class, a class over a pattern. |
| Speculative Generality, Dead Code | Nothing is built for a requirement that does not exist yet. Ideas go to Future Scope, not into the code. |
| Comments | Names explain *what*. Comments are kept for *why* (for example, why UTM is not used above 84°N). |
| Temporary Field | Objects are complete when created; no fields that are filled in "later". |

Techniques used on purpose: Replace Magic Number with Symbolic Constant (UTM limits, size caps),
Replace Nested Conditional with Guard Clauses, Replace Error Code with Exception, Replace Type Code
with Class (enums), Introduce Parameter Object, Extract Method.

## Patterns

The site's own criticism page sets the bar: a pattern is justified only by a real problem, patterns
applied "to the letter" produce inefficient code, and in a language with first-class functions a
Strategy can be a function.

| Pattern | Verdict | Why |
| --- | --- | --- |
| Strategy | Used, in its light form | File formats differ in how they are validated and read; each format is a reader object behind one interface. Measurement type by geometry type is a lookup table of functions. |
| Facade | Used | One service is the only thing the API layer calls. It hides readers, geometry and persistence. Kept small so it does not become a god object. |
| Adapter (idea only) | Used at one boundary | Readers convert what GDAL and GeoPandas return into our own feature objects, so no other layer depends on those libraries' shapes. |
| Factory Method | Rejected | It needs a creator class hierarchy. A dictionary from format to reader does the same job; the smells page itself accepts a simple selection for object creation. |
| Template Method | Rejected | The shared order of steps lives in the service, and readers are composed, not inherited. The pattern's listed costs (a rigid skeleton, subclasses that break substitution) buy nothing here. |
| Singleton | Rejected | Settings and database sessions are passed in through dependency injection. A singleton hides coupling and makes tests harder, both listed as costs. |

## API rules

- Resources are plural nouns; HTTP methods are the verbs. No verbs in paths. Nesting stops at
  collection/item/collection (`/api/files/{id}/measurements/`).
- JSON in and out, snake_case fields. Multipart only for the file upload itself.
- Responses are a view of the domain, not a mirror of the database tables.
- Status codes: 201 with a `Location` header and the resource for a created upload; 200 for reads;
  400 for a malformed request; 404 for an unknown id; 409 when the resource's state does not allow
  the request; 413 for an oversized upload; 415 for an unsupported file type; 422 for a well-formed
  upload whose content cannot be processed; 500 with no internal detail.
- One error shape everywhere: RFC 9457 Problem Details (`application/problem+json`). Messages help
  the caller fix the request and never expose stack traces or paths.
- Collections are paginated with `limit` and `offset`, with documented defaults and a maximum (the
  Microsoft guide: an upper limit protects against denial of service). Pagination metadata is in the body.
- GET is safe and idempotent. POST is not, and the server assigns the id and URI.
- Responses carry links to related resources, so a client does not build URLs by hand.
- Long-running work is the 202 Accepted plus status-resource pattern. This service processes inside
  the request and exposes `status` on the resource, so moving to 202 later does not change the resource shape.
- Versioning: the assignment fixes the paths as `/api/...`. Additive changes need no version; a
  breaking change would be introduced as `/api/v2/...` alongside the existing paths.
- Every request gets a request id, returned in `X-Request-ID` and written to the logs.
- Security: validate everything, cap sizes, never use a client filename as a path, HTTPS in production.
- The OpenAPI document is generated from the code and served at `/docs`.
