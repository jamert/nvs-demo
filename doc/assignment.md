# Nevis Home Assignment

This exercise is designed to simulate a realistic feature you might work on with us.

You may use **one of the backend languages** (Java/Kotlin, Python).

We are building a WealthTech automation platform for advisors, who need to **search across clients and clients' documents** quickly and intelligently.

Your task is to implement a simplified **Search API** across clients and documents that supports following cases:

- Find clients for matches in their emails/name/description. E.g. request "NevisWealth" should return client with email "john.doe@neviswealth.com"
- Find documents based on similar terms from its content. E.g. searching for "address proof" should also return documents containing "utility bill".
- Optional: Quick summary of document content.

## Requirements

We encourage you to use LLMs to implement solutions as best as possible.

### Open API Endpoints and data model

Follow REST conventions and return proper HTTP codes. Document the API (Swagger or Markdown) and extend model responses when it's needed.

See the [OpenAPI 3.1 specification](openapi.yml) for the endpoints and data models.

## Deliverables

- Source code in a repo.
- docker-compose for reproducibility.
- Tests for core logic and edge cases.
- README.md with:
  - Setup instructions
  - Example search queries and responses
- API documentation (Swagger or Markdown).
- If you can deploy it somewhere and provide us credentials to API - will be a plus

## Expected Effort

- Estimated time: up to 10-14 hours (depending on stack & familiarity).
- Expected turnaround: 2–3 days of focused work, or up to 1 week if done part-time.

---

## Communication

If you have any **questions or blockers**, please reach out to **Grigory Sobko & CC your recruiter Ksenia Filimonova** (grigory.sobko@neviswealth.com & ksenia.filimonova@neviswealth.com )

This task is designed to test both **technical implementation skills** and **decision-making tradeoffs**. Please balance correctness, clarity, and simplicity in your solution.
