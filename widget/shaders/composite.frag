#version 440
// 把边长 2 倍的离屏画布缩小一半画到目标上（线性过滤 = 每个像素平均 4 个样本），顺便去色、变淡。
layout(location = 0) in vec2 vUV;
layout(std140, binding = 0) uniform Composite {
    vec2 uScale;                           // 离屏画布只用了左下角这么大一块（画布按最大尺寸分配）
    float uGray;                           // 0..1 去色程度
    float uOpacity;                        // 0..1
    float uFlipV;                          // 1 = 贴图的第一行在上面（Metal），取样时上下颠倒
    float uTwice;                          // 1 = 颜色再乘一遍 alpha（上屏时用，见 dogview.py 的 TWICE）
};
layout(binding = 1) uniform sampler2D uTex;
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv = vUV * uScale;
    if (uFlipV > 0.5) uv.y = 1.0 - uv.y;
    vec4 c = texture(uTex, uv);                        // 预乘 alpha
    float g = dot(c.rgb, vec3(0.299, 0.587, 0.114));
    vec3 rgb = mix(c.rgb, vec3(g), uGray);
    rgb = mix(rgb, vec3(0.55) * c.a, 0.25 * uGray);   // 离线时对比度也降一点，更像留影
    vec4 o = vec4(rgb, c.a) * uOpacity;
    fragColor = vec4(o.rgb * mix(1.0, o.a, uTwice), o.a);
}
