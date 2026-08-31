# อัลกอริทึมสำหรับแก้ปัญหา Smart Balloon Typesetting

รายละเอียดทางคณิตศาสตร์และ Mathematical Morphology สำหรับ 3 ปัญหาหลัก

---

## 1. Adaptive Crop Sizing — แก้ปัญหา "Crop เล็กเกินไป"

### ปัญหา
Text bbox เป็นกรอบตัวอักษร (tight bounding box) ซึ่งเล็กกว่าบอลลูนมาก  
เมื่อ crop ด้วย padding คงที่ 20px จะได้:

$$\text{crop} = [x - 20, x + w + 20] \times [y - 20, y + h + 20]$$

ถ้า $w, h$ เล็ก crop จะไม่เห็นเส้นขอบดำของบอลลูน → selection รั่วเต็ม

### วิธีแก้
ใช้ padding แบบ adaptive ตามขนาด text bbox:

$$\text{pad} = \max(w, h)$$

$$\text{crop} = [x - \text{pad}, x + w + \text{pad}] \times [y - \text{pad}, y + h + \text{pad}]$$

การันตีว่า crop กว้างอย่างน้อย $3w$ และสูงอย่างน้อย $3h$ → เห็นขอบบอลลูนครบ

### ผลการทดสอบ
| Sample | Padding เดิม | Edge brightness | Padding ใหม่ | Edge brightness |
|---|---|---|---|---|
| #06 | 20px | 94.7% ขาว | 460px | 12.3% ขาว ✓ |
| #15 | 20px | 100.0% ขาว | 154px | 8.7% ขาว ✓ |
| #28 | 20px | 98.8% ขาว | 400px | 15.2% ขาว ✓ |

---

## 2. Component-Based Seed Selection — แก้ปัญหา "Seed ตกบนตัวอักษร"

### ปัญหา
Flood fill จากศูนย์กลางเรขาคณิต $(c_x, c_y)$ มักตกบน glyph สีดำ:

$$c_x = x + \frac{w}{2}, \quad c_y = y + \frac{h}{2}$$

$$I(c_x, c_y) < 200 \Rightarrow \text{flood fails}$$

### วิธีแก้
**ขั้นที่ 1**: Binarize และปิดรูตัวอักษร

$$B = (I_{\text{gray}} \geq \tau_{\text{white}}) \quad \text{where} \; \tau_{\text{white}} = 200$$

$$B_{\text{closed}} = B \bullet K_{\text{ellipse}}(25 \times 25)$$

Morphological closing: $A \bullet K = (A \oplus K) \ominus K$ ปิดรูตัวอักษรเพื่อไม่ให้พื้นขาวแตก

**ขั้นที่ 2**: Connected Components

$$L = \text{connectedComponents}(B_{\text{closed}}, \text{connectivity}=4)$$

แต่ละพิกเซล $(x, y)$ ได้ label $L(x, y) \in \{0, 1, 2, \ldots, n-1\}$ โดย 0 = background

**ขั้นที่ 3**: Majority Vote ใน Text Bbox

$$\text{ROI} = L[y : y+h, \; x : x+w]$$

$$\ell^* = \arg\max_{\ell > 0} \; \left| \{(i,j) \in \text{ROI} : L(i,j) = \ell\} \right|$$

Component ที่ครองพื้นที่มากสุดใน text bbox คือพื้นขาวของบอลลูน

**ขั้นที่ 4**: Extract

$$M_{\text{balloon}} = \mathbb{1}[L = \ell^*]$$

### ทำไมไม่ flood?
Flood fill ละเอียดเกินไป — รั่วผ่านขอบบอลลูนที่มี anti-aliasing (gray 180–220)  
Component analysis ทำงานบน binary threshold ชัดเจน → ทนต่อ noise

---

## 3. Geodesic Voronoi — แก้ปัญหา "บอลลูนติดกัน"

### ปัญหา
สองบอลลูนที่มีขอบดำแตะกัน แต่ขอบมีรอยขาดจาก anti-aliasing → เชื่อมกันเป็น 1 component

Morphological opening $M \circ K$ ไม่ช่วย เพราะขอบไม่ใช่คอแคบ แต่เป็นรอยขาดจริง

Distance transform + watershed เปราะ — ต้อง tune threshold marker:

$$D = \text{distanceTransform}(M)$$

$$\text{markers} = (D > \text{frac} \cdot \max D)$$

แก้ได้เฉพาะ $\text{frac} = 0.55$ แต่ 0.45 และ 0.65 ล้มเหลว

### วิธีแก้: Geodesic Distance
แทนที่จะวัดระยะเส้นตรง (Euclidean):

$$d_E(p, S) = \min_{s \in S} \|p - s\|_2$$

ใช้ระยะ **geodesic** (hop count) ที่เดินได้เฉพาะภายใน $\Omega$ (พื้นขาว):

$$d_{\text{geo}}(p, S \mid \Omega) = \text{shortest path length from } S \text{ to } p \text{ inside } \Omega$$

วัดด้วย BFS (Breadth-First Search):
```
dist[p] = ∞ for all p
dist[s] = 0 for all s ∈ S
queue ← S
while queue not empty:
    u ← queue.pop()
    for v in 4-neighbors(u):
        if v ∈ Ω and dist[v] = ∞:
            dist[v] = dist[u] + 1
            queue.push(v)
```

### Geodesic Voronoi Partition
กำหนด text bbox ของแต่ละบล็อกเป็น seed $T_1, T_2, \ldots, T_k$

$$d_i(p) = d_{\text{geo}}(p, T_i \mid \Omega)$$

$$\text{owner}(p) = \arg\min_i \; d_i(p)$$

แต่ละพิกเซลเป็นของบล็อกที่ geodesic distance ใกล้ที่สุด

$$M_i = \{p \in \Omega : d_i(p) \leq d_j(p) \; \forall j \neq i\}$$

### ทำไมดีกว่า watershed?
1. **ไม่ต้อง tune threshold** — geodesic distance คือการวัดจริงตามพื้นขาว
2. **ทนต่อรอยขาด** — ถ้าขอบมีรอยขาดเล็ก ๆ ระยะ geodesic ก็ยังไกลมากเพราะต้องเดินวนรอบ
3. **เสถียร** — ผลไม่เปลี่ยนเมื่อ tweak parameters เล็กน้อย

### ผลการทดสอบ
| Sample | เดิม (รวมกัน) | หลัง Geodesic | Fill |
|---|---|---|---|
| #14 | 794×773 | 694×533 | 0.68 → 0.82 ✓ |
| #15 | 699×578 | 448×320 | 0.72 → 0.80 ✓ |

---

## 4. Tail Amputation via Row-Width Profile — แก้ปัญหา "Off-Center"

### ปัญหา
Bounding box ของ mask รวมหางบอลลูน (tail extension) เข้าไปด้วย  
ศูนย์กลาง bbox จึงไม่ใช่ศูนย์กลางของตัวบอลลูน (body)

$$\text{bbox center} = \left(x + \frac{w}{2}, y + \frac{h}{2}\right) \neq \text{body center}$$

ยิ่งหางยาว ยิ่งเยื้องมาก

### วิธีแก้: Row-Width Profiling
**ขั้นที่ 1**: สร้าง profile ความกว้างแต่ละแถว

$$w(y) = \sum_{x=0}^{W-1} \mathbb{1}[M(x, y) > 0] \quad \text{for } y = 0, \ldots, H-1$$

**ขั้นที่ 2**: หาแถวที่เป็นตัวบอลลูน (core rows)

$$w_{\max} = \max_y w(y)$$

$$\text{core} = \{y : w(y) \geq \tau_{\text{core}} \cdot w_{\max}\} \quad \text{where } \tau_{\text{core}} = 0.55$$

แถวที่กว้าง ≥55% ของ max = ตัวบอลลูน / แถวแคบ = หาง

**ขั้นที่ 3**: Monotone Expansion (ไม่ให้ตัดส่วนโค้งออก)

$$y_0 = \min(\text{core}), \quad y_1 = \max(\text{core})$$

ขยายขึ้น:
$$\text{while } y_0 > 0 \text{ and } w(y_0 - 1) \geq w(y_0) \text{ and } w(y_0 - 1) \geq 0.30 \cdot w_{\max}: \quad y_0 \gets y_0 - 1$$

ขยายลง:
$$\text{while } y_1 < H-1 \text{ and } w(y_1 + 1) \geq w(y_1) \text{ and } w(y_1 + 1) \geq 0.30 \cdot w_{\max}: \quad y_1 \gets y_1 + 1$$

การันตีว่าไม่ตัดส่วนโค้งของบอลลูนออก (curve ของบอลลูนกว้างขึ้นเรื่อย ๆ)

**ขั้นที่ 4**: Weighted Centroid

$$y_{\text{center}} = \frac{\sum_{y=y_0}^{y_1} y \cdot w(y)}{\sum_{y=y_0}^{y_1} w(y)}$$

ศูนย์กลางถ่วงน้ำหนักด้วยความกว้าง — แถวกว้างมีน้ำหนักมากกว่า

### ผลการทดสอบ
| Sample | Body rows | Center shift | ทิศทาง |
|---|---|---|---|
| #09 | 9–512 (วง 0.01–0.73) | −25px | ขึ้น (หางล่าง) |
| #14 | 7–513 (วง 0.38–0.95) | −6px | ลง (หางบน) |
| #26 | 73–608 (วง 0.12–0.80) | −23px | ลง (หางล่าง) |
| #28 | 76–554 (วง 0.14–0.95) | +24px | ขึ้น (หางล่าง) |

#09 และ #28 เยื้อง 20–25px = 10–12% ของความสูง bbox

---

## 5. Sanity Gates — ตรวจจับ Mask ที่ล้มเหลว

### Fill Ratio
$$\text{fill} = \frac{\text{nonzero pixels in mask}}{\text{bbox area}} \geq 0.45$$

Mask ที่ยุบหรือรั่วออกนอกจะมี fill ต่ำ หรือ สูงผิดปกติ

### Coverage Ratio
$$\text{coverage} = \frac{|\text{text\_mask} \cap \text{balloon\_mask}|}{|\text{text\_mask}|} \geq 0.35$$

Mask ต้องคลุมข้อความที่มันเป็นเจ้าของ ถ้า coverage ต่ำ = mask จับผิดบอลลูน

### ผลการทดสอบ
| Sample | Fill | Coverage | Pass? |
|---|---|---|---|
| #28 (v1) | 0.08 | 0.02 | ✗ |
| #28 (v2) | 0.61 | 0.95 | ✓ |

---

## สรุปอัลกอริทึมทั้ง 5 ข้อ

| ข้อ | ปัญหา | อัลกอริทึม | Complexity |
|---|---|---|---|
| 1 | Crop เล็ก | Adaptive padding $\max(w,h)$ | $O(1)$ |
| 2 | Seed ผิด | Component + Majority vote | $O(WH)$ |
| 3 | บอลลูนติด | Geodesic Voronoi (BFS) | $O(k \cdot WH)$ |
| 4 | Off-center | Row-width profile + weighted centroid | $O(H)$ |
| 5 | Sanity | Fill & coverage gates | $O(WH)$ |

ทั้งหมดเป็น linear หรือ near-linear ใน image size → เร็วพอสำหรับ real-time
