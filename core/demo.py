"""Curated sample: first-run experience without an API key."""
from core.extractor import MathConcept, ExtractionResult, connect_concepts

DEMO_TEXT = r"""User: 能解释导数、泰勒公式和麦克劳林公式之间的联系吗？顺便讲一下矩阵的行列式。

Assistant: 导数刻画函数局部的变化率。泰勒公式利用同一点的各阶导数构造局部多项式近似；在 0 点展开时就是麦克劳林公式。矩阵的行列式是另一个独立主题，不需要强行与泰勒公式建立关系。

User: 请保留条件、余项和矩阵公式，并说明如何近似指数函数。

Assistant: 对 n+1 次连续可微函数，泰勒展开需要保留拉格朗日余项；无限级数还需要收敛到原函数的额外条件。对于指数函数，麦克劳林级数为 e^x = sum x^n/n!。导数的简单例题是 f(x)=x²：展开 (x+h)²-x² 后除以 h，差商是 2x+h，令 h 趋于 0 得导数 2x。"""


def demo_result():
    concepts = [
        MathConcept("导数", "定义", "微积分", r"""## 定义

导数描述函数在一点附近的瞬时变化率。当以下极限存在时，定义

$$f'(a)=\lim_{h\to 0}\frac{f(a+h)-f(a)}{h}.$$

函数的高阶导数为泰勒公式提供系数。可导意味着在该点连续，反之不一定成立。

## 例题

求 $f(x)=x^2$ 的导数，结果为 $f'(x)=2x$。

## 证明

从定义出发，差商可以写为

$$\frac{(x+h)^2-x^2}{h}=2x+h\quad(h\ne0).$$

因此 $\lim_{h\to0}(2x+h)=2x$，即 $f'(x)=2x$。
""", tags=["局部近似"]),
        MathConcept("泰勒公式", "定理", "微积分", r"""## 适用条件

设 $n\ge0$ 为整数，$f$ 在包含 $a$ 与 $x$ 的开区间内有 $n+1$ 阶连续导数。这个充分条件保证以下拉格朗日余项形式成立。

## 定理

$$f(x)=\sum_{k=0}^{n}\frac{f^{(k)}(a)}{k!}(x-a)^k+R_n(x).$$

其中 $R_n(x)$ 是余项；不能直接将有限阶公式等同于无限级数。

## 拉格朗日余项

在上述条件下，对于 $x\ne a$，存在严格介于两者之间的 $\xi$，使

$$R_n(x)=\frac{f^{(n+1)}(\xi)}{(n+1)!}(x-a)^{n+1}.$$

---

## 例题

\[
\begin{aligned}
e^x &\approx 1+x+\frac{x^2}{2},\\
\sin x &\approx x-\frac{x^3}{6}.
\end{aligned}
\]

麦克劳林公式是选择 $a=0$ 的特例。
""", tags=["泰勒展开", "余项"]),
        MathConcept("麦克劳林公式", "方法", "微积分", r"""## 在零点展开

麦克劳林公式是泰勒公式在 $a=0$ 时的形式：

$$f(x)=\sum_{k=0}^{n}\frac{f^{(k)}(0)}{k!}x^k+R_n(x).$$

对于指数函数，其幂级数在所有实数 $x$ 上收敛到原函数：

$$e^x=\sum_{k=0}^{\infty}\frac{x^k}{k!}.$$

这说明零点处的导数信息可以用来构造函数近似。
""", tags=["幂级数"]),
        MathConcept("矩阵与行列式", "定义", "线性代数", r"""## 二阶行列式

\[
A=\begin{pmatrix}a&b\\c&d\end{pmatrix},\qquad\det A=ad-bc.
\]

当 $\det A\ne 0$ 时，矩阵可逆：

$$A^{-1}=\frac{1}{ad-bc}\begin{pmatrix}d&-b\\-c&a\end{pmatrix}.$$

分段条件也可以直接预览：

$$g(x)=\begin{cases}x^2,&x\ge 0,\\-x,&x<0.\end{cases}$$

该主题与本次对话中的泰勒展开没有明确联系，因此保留为独立笔记。
""", tags=["矩阵", "可逆性"]),
    ]
    edges = connect_concepts(concepts, [
        dict(source="泰勒公式", target="导数", relation="依赖", reason="展开系数由同一点的各阶导数决定。"),
        dict(source="麦克劳林公式", target="泰勒公式", relation="特例", reason="将泰勒公式的展开点选为零。"),
        dict(source="麦克劳林公式", target="导数", relation="应用", reason="利用零点处的各阶导数计算多项式系数。"),
    ])
    return ExtractionResult(True, 1.0, concepts, "从导数到局部近似：泰勒与麦克劳林公式，以及独立的矩阵主题。", connections=edges, source="内置教学示例")
