# ADR-001: ใช้ PostgreSQL เป็น Host Source of Truth และแยก GPU Worker ออกจาก API

## Status

Accepted

## Context

Houmi เดิมเป็น Desktop application ที่ใช้ FastAPI, SQLite, in-process background tasks และโหลด OCR/ML models จาก FastAPI lifespan โดยตรง การนำระบบไปเป็น Host ที่รับผู้ใช้หลายคนต้องรองรับ tenant isolation, remote jobs, recovery และการ restart service โดยไม่ทำให้ข้อมูลหรืองานหาย

## Decision

- Local Mode ใช้ SQLite และ local filesystem ต่อไป
- Host Mode บังคับใช้ PostgreSQL ผ่าน Alembic migrations
- PostgreSQL เป็น source of truth ของ users, projects, assets, licenses, jobs และ job events
- Redis/Arq ใช้เป็น dispatcher/notification mechanism ไม่ใช่แหล่งข้อมูลหลัก
- FastAPI ทำหน้าที่รับคำขอและสร้าง/อ่านสถานะ Job
- GPU Worker เป็น process แยก โหลด model และเขียนผลผ่าน Asset/Job service
- Production startup จะไม่เรียก `Base.metadata.create_all()`

## Rationale

1. PostgreSQL รองรับ concurrent transactions และ row locking ที่จำเป็นต่อ atomic redeem และ job recovery
2. การแยก Worker ป้องกันไม่ให้ GPU/OCR lifecycle ผูกกับ API process
3. Local SQLite ยังรักษา UX แบบ offline และไม่เพิ่ม infrastructure ให้ผู้ใช้เดี่ยว
4. การให้ Database เป็น source of truth ช่วยกู้ระบบได้เมื่อ Redis หรือ Worker restart

## Trade-offs

- Host ต้องดูแล PostgreSQL, Redis, backup และ migrations
- ต้องมี service layer ใหม่เพื่อแยก route logic จาก inference logic
- Local และ Host ต้องมี database configuration และ migration path แยกกัน

## Consequences

- Existing SQLite data ต้องมี explicit migration/import strategy
- Worker ต้องมี heartbeat, lease fencing และ idempotent result writes
- Public API ต้องไม่ส่ง absolute filesystem paths

## Revisit Trigger

- จำนวนผู้ใช้หรือ job concurrency ต่ำมากจน PostgreSQL/Redis เป็นภาระเกินความจำเป็น
- เปลี่ยนจาก single-host deployment ไป managed queue/object storage
