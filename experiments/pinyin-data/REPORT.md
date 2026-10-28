# 魔光键影 · 拼音数据报告

- 生成日期：2026-10-28
- 词表：`D:\Tanimodori\Projects\@FF14\ff7-ime\dict.txt`
- 提取脚本：`D:\Tanimodori\Projects\@FF14\ff7-ime\experiments\pinyin-data\extract.py`
- 覆盖表：`D:\Tanimodori\Projects\@FF14\ff7-ime\experiments\pinyin-data\override.yaml`

## 1. 概览

| 指标 | 数值 |
| --- | ---: |
| 词条数 | 1212 |
| 原始行数 | 1212 |
| 汉字总出现次数 | 5560 |
| 唯一汉字数 | 1326 |
| 多音字（pypinyin heteronym > 1） | 576 |
| 语料内实际出现多读的字 | 28 |
| 人工覆盖字 / 实际改动词 | 23 / 48 |
| 整词人工确认 | 62 |
| pypinyin 与 luna 首选冲突 | 1（已解决 1） |
| 最终读音与 luna 冲突（未解决） | 0（已知漏收 1） |
| pypinyin 缺失字 | 0 |
| luna 缺失字 | 0 |
| terra 缺失字 | 2 |
| 两套数据都缺失的字 | 0 |
| 标点种类 / 出现次数 | 6 / 127 |

验收结论：

- 覆盖 **1212/1212** 条，每条至少一个主读音。
- 生僻字缺失 **0**；所有唯一汉字均由 pypinyin 与 luna 双源覆盖。
- 多音字、误读候选均以结构化列输出，Lua 可直接消费。

## 2. 输入解析

`dict.txt` 为 UTF-16 LE + BOM、CRLF 换行。解析步骤：

1. 按 BOM 判定 `utf-16` 解码（兼容无 BOM 的 UTF-8）。
2. `splitlines()` 同时处理 `\r\n` / `\n`。
3. 去掉每行首尾空白；跳过空行（本词表实际无空行）。
4. `id` 按有效词条顺序 1..N 递增；`line_no` 保留原始物理行号。

本次结果：原始行 1212，有效词条 1212，空行 0。

## 3. 注音方法

优先级从高到低：

1. `override.yaml` 的 `confirmed_phrases`（整词人工确认，最权威）。
2. `override.yaml` 的 `char_rules`（上下文规则，如“长杖”的“长”读 cháng）。
3. `override.yaml` 的 `char_defaults`（单字默认，如“曾”读 zēng）。
4. `pypinyin` 词组模式（含其内置词组表）。
5. `pypinyin` 单字首选。

其他约定：

- 连续汉字串分别调用 pypinyin，避免标点影响分词；标点原样保留在 `phrase`。
- 无调全拼：去掉数字声调，`ü` 写作 `v`（`女 nv`、`绿 lv`、`略 lve`），与 Rime 全拼一致。
- 数字声调：1–4 为四声，5 表示轻声。
- `一`、`不` 统一标本调 `yi1` / `bu4`，不记录语流变调；无调全拼不变。
- `per_char_readings` 形如 `字:yin1|yin2`，主读音在前。
- `alt_readings` 为 JSON 数组，按汉字位置对齐，避免同词重复字冲突。
- 输出文件为 UTF-8（无 BOM）、LF 换行、无 CSV 引号；JSON 列是原始 JSON，可直接解析。

## 4. 数据源与交叉校验

- pypinyin：0.55.0
- luna_pinyin：`C:\Program Files\Rime\weasel-0.17.4\data\luna_pinyin.dict.yaml`（单字条目 41344）
- terra_pinyin：`C:\Program Files\Rime\weasel-0.17.4\data\terra_pinyin.dict.yaml`（单字条目 41274）

校验口径：

- **首选冲突**：pypinyin 单字首选的无调形式不在 luna 该字读音集合中。
- **最终冲突**：`phrases.tsv` 中每个音节的无调形式不在 luna 该字读音集合中。
- luna/terra 的多音字可能多行或一行多音节，均已展开为集合。
- 逐字差异可直接对比 `chars.tsv` 的 `heteronyms` 与 `luna_readings` / `terra_readings` 列；`pypinyin_luna_conflict=1` 标记 pypinyin 首选与 luna 冲突。

结果：首选冲突 1 处，全部通过人工覆盖解决；最终冲突 0 处。

| 字 | pypinyin 首选 | luna | 处理 |
| --- | --- | --- | --- |
| 掴 | guai1 | guo | 人工确认/覆盖为 guo2 |

另有 luna 漏收、但规范有据的已知差异 1 处，单列如下，不计为失败。

| 词条 | 字 | 本表读音 | luna 读音 | 说明 |
| --- | --- | --- | --- | --- |
| 巴拔维拉缪 | 缪 | miu4 | miao/mou | luna 只收 miao/mou，漏收 miù；《现代汉语词典》缪 miù（纰缪、缪斯） |

异构读音集合差异（不是错误，仅说明数据源覆盖不同）：

- luna 有而 pypinyin heteronym 未列出的字：85 个
- terra 有而 pypinyin heteronym 未列出的字：18 个

luna 额外读音示例：猎(ji)、区(gou)、我(e)、把(bai)、和(han)、隔(jie)、盖(he)、乔(jiao)、什(she)、黑(he)、色(she)、啊(o)、圣(guai)、窟(jiao)、会(gui)、哈(ka)、备(yuan)、入(ri)、爸(bei)、射(shi)

## 5. 多音字

语料共 1326 个唯一汉字，其中 576 个在 pypinyin 中具有多个读音；28 个在本语料中实际出现了不止一种读音。

按语料出现次数排序的前 30 个多音字（完整数据见 `chars.tsv`）：

| 字 | 次数 | 语料主读音 | 语料内读音分布 | pypinyin 全部读音 |
| --- | ---: | --- | --- | --- |
| 的 | 105 | de5 | de5×105 | de5|di1|di2|di4 |
| 之 | 47 | zhi1 | zhi1×47 | zhi1|zhu1|zhi4 |
| 神 | 39 | shen2 | shen2×39 | shen2|shen1 |
| 是 | 32 | shi4 | shi4×32 | shi4|ti2 |
| 古 | 31 | gu3 | gu3×31 | gu3|gu4|ku1 |
| 斯 | 31 | si1 | si1×31 | si1|shi3 |
| 罗 | 28 | luo2 | luo2×28 | luo2|luo1 |
| 石 | 25 | shi2 | shi2×25 | shi2|dan4 |
| 不 | 24 | bu4 | bu4×24 | bu4|fou3|fou1|fu1|bu2 |
| 鸟 | 23 | niao3 | niao3×23 | niao3|diao3 |
| 大 | 22 | da4 | da4×22 | da4|dai4|tai4 |
| 巨 | 22 | ju4 | ju4×22 | ju4|qu2 |
| 给 | 22 | gei3 | gei3×22 | gei3|ji3 |
| 莫 | 22 | mo4 | mo4×22 | mo4|mu4 |
| 行 | 22 | xing2 | xing2×22 | xing2|hang2|heng2|xing4|hang4 |
| 了 | 21 | le5 | le5×20、liao3×1 | le5|liao3|liao4 |
| 一 | 18 | yi1 | yi1×18 | yi1|yi2|yi4 |
| 吧 | 17 | ba5 | ba5×17 | ba5|ba1|pa1 |
| 斗 | 17 | dou4 | dou4×14、dou3×3 | dou4|dou3|zhu3 |
| 爆 | 17 | bao4 | bao4×17 | bao4|bo2 |
| 金 | 17 | jin1 | jin1×17 | jin1|jin4 |
| 长 | 17 | chang2 | chang2×13、zhang3×4 | chang2|zhang3 |
| 拉 | 16 | la1 | la1×16 | la1|la2|la3|la4|la5 |
| 机 | 16 | ji1 | ji1×16 | ji1|wei4 |
| 重 | 16 | zhong4 | zhong4×10、chong2×6 | zhong4|chong2|tong2 |
| 高 | 16 | gao1 | gao1×16 | gao1|gao4 |
| 地 | 15 | di4 | di4×14、de5×1 | di4|de5 |
| 场 | 15 | chang3 | chang3×14、chang2×1 | chang3|chang2 |
| 尼 | 15 | ni2 | ni2×15 | ni2|ni3 |
| 弹 | 15 | dan4 | dan4×14、tan2×1 | dan4|tan2 |

重点多音字（语料上下文决定）：

| 字 | 语料主读音 | 反例/其他读音 | 说明 |
| --- | --- | --- | --- |
| 长 | chang2 | zhang3 | 长杖/长靴 cháng；市长/村长 zhǎng |
| 重 | zhong4 | chong2 | 重拾 chóng；重逢/双重 chóng |
| 都 | dou1 | du1 | 都市/之都 dū；全都 dōu |
| 得 | de2 | dei3/de5 | 我得/得活着 děi；跑得掉 de |
| 了 | le5 | liao3 | 不得了 liǎo；走了 le |
| 弹 | dan4 | tan2 | 弹跳 tán；炸弹 dàn |
| 劲 | jin4 | jing4 | 劲歌 jìng；干劲 jìn |
| 嚼 | jiao2 | jue2 | 嚼嚼 jiáo |
| 什 | shen2 | shi2 | 什么 shén；美什 shí |
| 伽 | jia1 | ga1/qie2 | 吉尔伽美什 jiā |
| 勒 | le4 | lei1 | 华勒斯/盖恩斯伯勒 lè |
| 缪 | miu4 | mou2/miao4 | 巴拔维拉缪 miù |
| 曾 | zeng1 | ceng2 | 姓氏/人名 zēng |
| 辟 | bi4 | pi4 | 辟邪 bì |
| 杉 | shan1 | sha1 | 杉木 shān（又读 shā） |
| 谁 | shei2 | shui2 | 谁 shéi（又读 shuí） |
| 掴 | guo2 | guai1 | 掌掴 guó |
| 似 | si4 | shi4 | 似乎 sì |
| 脊 | ji3 | ji2 | 脊骨 jǐ |

## 6. 误读候选（读半边 / 形近误读）

`chars.tsv` 的 `misread_candidates` 列给出**允许的误读集合**，供 Lua 引擎做容错输入；它不等于规范读音，规范读音见 `primary` / `heteronyms`。

| 字 | 规范主读音 | 建议允许的误读 | 说明 |
| --- | --- | --- | --- |
| 榭 | xie4 | she4 | 罗榭/圣露榭 xiè；两源一致 |
| 獠 | liao2 | lao3 | 獠牙 liáo yá；两源一致 |
| 赭 | zhe3 | zhu1|chi4 | 赭红 zhě hóng；两源一致 |
| 梣 | cen2 | qin2|chen2 | 梣木 cén mù；pypinyin 另列 chen2/qin2 为备选 |
| 狲 | sun1 | xun4 | 猢狲 hú sūn；两源一致 |
| 猢 | hu2 | gu3 | 猢狲 hú sūn；两源一致 |
| 蚣 | gong1 | zhong1 | 蜈蚣 wú gōng；两源一致 |
| 的 | de5 | di1|di2|di4 |  |
| 斯 | si1 | shi1 |  |
| 克 | ke4 | ke1 |  |
| 德 | de2 | dei3 |  |
| 给 | gei3 | ji3 |  |
| 行 | xing2 | hang2 |  |
| 了 | le5 | liao3 |  |
| 镯 | zhuo2 | shu3 |  |
| 长 | chang2 | zhang3 |  |
| 重 | zhong4 | chong2 |  |
| 地 | di4 | de5 |  |
| 场 | chang3 | chang2 |  |
| 弹 | dan4 | tan2 |  |
| 陆 | lu4 | liu4 |  |
| 发 | fa1 | fa4 |  |
| 会 | hui4 | kuai4 |  |
| 强 | qiang2 | qiang3|jiang4 |  |
| 劳 | lao2 | lao1 |  |
| 卡 | ka3 | qia3 |  |
| 中 | zhong1 | zhong4 |  |
| 哈 | ha1 | ha3|he2 |  |
| 圈 | quan1 | juan4 |  |
| 菲 | fei1 | fei3 |  |
| 诺 | nuo4 | ruo4 |  |
| 这 | zhe4 | zhei4 |  |
| 头 | tou2 | tou5 |  |
| 得 | de2 | dei3|de5 |  |
| 角 | jiao3 | jue2 |  |
| 为 | wei2 | wei4 |  |
| 子 | zi3 | zi5 |  |
| 杜 | du4 | du3 |  |
| 结 | jie2 | jie1 |  |
| 蕾 | lei3 | lei2 |  |

译名中重点防范的误读：

| 字 | 规范读音 | 常见误读 | 例词 |
| --- | --- | --- | --- |
| 蒂 | di4 | ti4 | 蒂法、克劳蒂亚·斯特莱夫 |
| 克 | ke4 | ke1 | 克劳德、克劳蒂亚·斯特莱夫、扎克斯 |
| 劳 | lao2 | lao1 | 克劳德、克劳蒂亚·斯特莱夫 |
| 德 | de2 | dei3 | 克劳德、海德格、路德 |
| 萨 | sa4 | sa1 | 萨菲罗斯、英雄萨菲罗斯 |
| 菲 | fei1 | fei3 | 萨菲罗斯、菲拉、尤菲 |
| 蕾 | lei3 | lei2 | 艾蕾诺雅、玛蕾、史卡蕾特 |
| 榭 | xie4 | she4 | 罗榭、圣露榭、榭札蟹 |
| 赭 | zhe3 | zhu1|chi4 | 赭红猎犬、赭红浮游死神 |
| 猢 | hu2 | gu3 | 猢狲木 |
| 狲 | sun1 | xun4 | 猢狲木 |
| 梣 | cen2 | qin2|chen2 | 梣木 |
| 诺 | nuo4 | ruo4 | 雷诺、杰诺瓦、诺艾米 |
| 洛 | luo4 | ge4 | 蒂法·洛克哈特、布洛德、格伦·洛斯布鲁克上校 |
| 勒 | le4 | lei1 | 华勒斯、盖恩斯伯勒 |
| 缪 | miu4 | mou2|miao4 | 巴拔维拉缪 |
| 伽 | jia1 | qie2|ga1 | 吉尔伽美什、吉尔伽美什光束 |
| 什 | shen2 | shi2 | 吉尔伽美什、吉尔伽美什光束 |

## 7. 译名与专名确认

| 词条 | 无调全拼 | 数字声调 | 说明 |
| --- | --- | --- | --- |
| 蒂法 | di fa | di4 fa3 | Tifa；蒂 dì，不读 tì |
| 克劳德 | ke lao de | ke4 lao2 de2 | Cloud；克 kè，劳 láo，德 dé |
| 巴雷特 | ba lei te | ba1 lei2 te4 | Barret；巴 bā，雷 léi，特 tè |
| 爱丽丝 | ai li si | ai4 li4 si1 | Aerith；爱 ài，丽 lì，丝 sī |
| 萨菲罗斯 | sa fei luo si | sa4 fei1 luo2 si1 | Sephiroth；萨 sà，菲 fēi，罗 luó，斯 sī |
| 扎克斯 | zha ke si | zha1 ke4 si1 | Zack；扎 zhā，不读 zā |
| 雷诺 | lei nuo | lei2 nuo4 | Reno；诺 nuò，不读 ruò |
| 路德 | lu de | lu4 de2 | Rude；路 lù，德 dé |
| 曾 | zeng | zeng1 | Tseng；姓氏/人名读 zēng，不读 céng |
| 宝条 | bao tiao | bao3 tiao2 | Hojo；宝 bǎo，条 tiáo |
| 五台 | wu tai | wu3 tai2 | Wutai；五 wǔ，台 tái |
| 神罗 | shen luo | shen2 luo2 | Shinra；神 shén，罗 luó |
| 蒂法·洛克哈特 | di fa luo ke ha te | di4 fa3 luo4 ke4 ha1 te4 | Tifa Lockhart；间隔号“·”不注音 |
| 吉尔伽美什 | ji er jia mei shi | ji2 er3 jia1 mei3 shi2 | Gilgamesh；伽 jiā，什 shí |
| 巴拔维拉缪 | ba ba wei la miu | ba1 ba2 wei2 la1 miu4 | 译名；缪 miù，不读 móu |
| 忘却之都 | wang que zhi du | wang4 que4 zhi1 du1 |  |

特别确认：

- “蒂”读 **dì**，不读 tì；蒂法 = `di fa`。
- “曾”作姓氏/人名读 **zēng**，不读 céng；曾 = `zeng`。
- “宝条”的“条”读 **tiáo**；宝条 = `bao tiao`。
- “五台”的“台”读 **tái**；五台 = `wu tai`。
- “神罗”= `shen luo`；“雷诺”= `lei nuo`；“路德”= `lu de`。
- 含间隔号的名字只对汉字注音，`·` 不参与。

## 8. 生僻字与缺失

- 两套数据都缺失：**0**。
- pypinyin 缺失：**0**。
- luna 缺失：**0**。
- terra 缺失：**2**（们、吗）。

重点生僻字核对表（含未出现在 dict.txt 的观察字）：

| 字 | 读音 | 是否在词表 | 来源 | 说明 |
| --- | --- | --- | --- | --- |
| 赭 | zhe3 | 是 | pypinyin+luna | 赭红 zhě hóng；两源一致 |
| 榭 | xie4 | 是 | pypinyin+luna | 罗榭/圣露榭 xiè；两源一致 |
| 蚣 | gong1 | 是 | pypinyin+luna | 蜈蚣 wú gōng；两源一致 |
| 猢 | hu2 | 是 | pypinyin+luna | 猢狲 hú sūn；两源一致 |
| 狲 | sun1 | 是 | pypinyin+luna | 猢狲 hú sūn；两源一致 |
| 梣 | cen2 | 是 | pypinyin+luna | 梣木 cén mù；pypinyin 另列 chen2/qin2 为备选 |
| 鼬 | you4 | 否 | pypinyin | 未出现在 dict.txt；读 yòu，易误读 yóu（由） |
| 獠 | liao2 | 是 | pypinyin+luna | 獠牙 liáo yá；两源一致 |
| 蠍 | xie1 | 否 | pypinyin | 未出现在 dict.txt；“蝎”的异体，读 xiē，易误读 jié（竭） |
| 糠 | kang1 | 否 | pypinyin | 未出现在 dict.txt；读 kāng，易误读 kàn/kǎng |
| 颚 | e4 | 否 | pypinyin | 未出现在 dict.txt；读 è（上颚/下颚），易误读 é（额） |
| 岑 | cen2 | 否 | pypinyin | 未出现在 dict.txt；读 cén，易误读 qín |

所有出现在词表中的生僻字均为 pypinyin 与 luna 双源一致，因此不存在无依据读音。

## 9. 已知风险与限制

1. **词组表误判**：pypinyin 的词组表并非为 FF7 译名设计，已发现并修正：
   - 长杖 / 长靴被误读为 zhǎng；
   - 重拾被误读为 zhòng；重拾 = chóng shí；
   - 劲歌被误读为 jìn；劲歌 = jìng gē；
   - 都给“之都”误读为 dōu；都 = dū；
   - 得在“我得…”“得活着…”中误读为 dé；应读 děi；
   - 了在“不得了”中误读为 le；应读 liǎo；
   - 弹跳被误读为 dàn；应读 tán；
   - 嚼被误读为 jué；嚼嚼 = jiáo jiáo；
   - 吉尔伽美什被误读为 gā/měi shén；应读 jiā/měi shí；
   - 华勒斯/盖恩斯伯勒的“勒”被误读为 lēi；应读 lè；
   - 巴拔维拉缪的“缪”被误读为 móu；应读 miù。
2. **轻声标注**：词典对部分轻声词有不同处理（如“骰子”的“子”）；本表按普通话口语标轻声 5，无调全拼不受影响。
3. **一/不 变调**：数字声调标本调，不标语流变调；若下游需要表面声调，应另行实现变调规则。
4. **译名用字**：FF7 中文译名存在多个版本（如 Aerith 有“爱丽丝/艾莉丝”），本表以 `dict.txt` 用字为准；仅对用字的普通话读音负责，不改写译名。
5. **多音字备选**：`heteronyms` 来自 pypinyin，可能包含书面/古音/异体读音；`primary` 是语料上下文主读音，不应把所有 heteronym 都当作可接受输入。
6. **误读集合**：`misread_candidates` 是人工整理的容错集合，不是规范读音；算法应把它与 `heteronyms` 区分使用。
7. **数据源版本**：pypinyin 与 Rime 词典版本变化可能改变个别读音；本报告对应版本见第 4 节。
8. **译名习惯差异**：“葛斯”（Gus）的“葛”按译名习惯取 gé；若按姓氏读 gě，需在 `override.yaml` 增加规则。类似地，“约达”取 yuē dá，若按 Yoda 译作“尤达”则另当别论。

## 10. 抽查样例

以下 35 条覆盖短词、长句、标点、多音字、生僻字、译名。

| id | 词条 | 无调全拼 | 数字声调 | 备注 |
| ---: | --- | --- | --- | --- |
| 1 | 神罗 | shen luo | shen2 luo2 | Shinra；神 shén，罗 luó |
| 2 | 蒂法 | di fa | di4 fa3 | Tifa；蒂 dì，不读 tì |
| 3 | 克劳德 | ke lao de | ke4 lao2 de2 | Cloud；克 kè，劳 láo，德 dé |
| 4 | 巴雷特 | ba lei te | ba1 lei2 te4 | Barret；巴 bā，雷 léi，特 tè |
| 24 | 塔克斯的制服为什么是黑色的啊！ | ta ke si de zhi fu wei shen me shi hei se de a | ta3 ke4 si1 de5 zhi4 fu2 wei4 shen2 me5 shi4 hei1 se4 de5 a5 | 标点不注音：！ |
| 40 | 爱丽丝 | ai li si | ai4 li4 si1 | Aerith；爱 ài，丽 lì，丝 sī |
| 41 | 扎克斯 | zha ke si | zha1 ke4 si1 | Zack；扎 zhā，不读 zā |
| 42 | 萨菲罗斯 | sa fei luo si | sa4 fei1 luo2 si1 | Sephiroth；萨 sà，菲 fēi，罗 luó，斯 sī |
| 72 | 罗榭 | luo xie | luo2 xie4 | Roche；榭 xiè；罗榭/圣露榭 xiè；两源一致 |
| 73 | 五台 | wu tai | wu3 tai2 | Wutai；五 wǔ，台 tái |
| 88 | 克劳蒂亚·斯特莱夫 | ke lao di ya si te lai fu | ke4 lao2 di4 ya4 si1 te4 lai2 fu1 | Claudia Strife；蒂 dì；标点不注音：· |
| 95 | 赭红猎犬 | zhe hong lie quan | zhe3 hong2 lie4 quan3 | 赭 zhě；赭红 zhě hóng；两源一致 |
| 129 | 曾 | zeng | zeng1 | 曾作姓氏/人名（Tseng）读 zēng，不读 céng |
| 148 | 宝条 | bao tiao | bao3 tiao2 | Hojo；宝 bǎo，条 tiáo |
| 186 | 巨蜈蚣 | ju wu gong | ju4 wu2 gong1 | 蜈蚣 wú gōng |
| 232 | 陆行鸟·山姆 | lu xing niao shan mu | lu4 xing2 niao3 shan1 mu3 | 标点不注音：· |
| 274 | 榭札蟹 | xie zha xie | xie4 zha2 xie4 | 榭 xiè，札 zhá；罗榭/圣露榭 xiè；两源一致 |
| 294 | 扎克斯·菲尔 | zha ke si fei er | zha1 ke4 si1 fei1 er3 | Zack Fair；菲尔 fēi ěr；标点不注音：· |
| 345 | 克劳德·斯特莱夫 | ke lao de si te lai fu | ke4 lao2 de2 si1 te4 lai2 fu1 | Cloud Strife；间隔号“·”不注音；标点不注音：· |
| 363 | 蒂法·洛克哈特 | di fa luo ke ha te | di4 fa3 luo4 ke4 ha1 te4 | Tifa Lockhart；间隔号“·”不注音；标点不注音：· |
| 366 | 爱丽丝·盖恩斯伯勒 | ai li si gai en si bo le | ai4 li4 si1 gai4 en1 si1 bo2 le4 | 译名华勒斯/盖恩斯伯勒的“勒”读 lè，不读 lēi；标点不注音：· |
| 770 | 猢狲木 | hu sun mu | hu2 sun1 mu4 | 猢 hú，狲 sūn；猢狲 hú sūn；两源一致 |
| 771 | 梣木 | cen mu | cen2 mu4 | 梣 cén，不读 qín；梣木 cén mù；pypinyin 另列 chen2/qin2 为备选 |
| 816 | 吉尔伽美什 | ji er jia mei shi | ji2 er3 jia1 mei3 shi2 | 吉尔伽美什的“伽”读 jiā，不读 gā/qié；吉尔伽美什的“什”读 shí，不读 shén |
| 844 | 嚼嚼弹跳 | jiao jiao tan tiao | jiao2 jiao2 tan2 tiao4 | 嚼嚼（咀嚼）读 jiáo，不读 jué；弹跳 = tán tiào；不读 dàn |
| 855 | 双重防御 | shuang chong fang yu | shuang1 chong2 fang2 yu4 |  |
| 950 | 怒发冲冠爆击 | nu fa chong guan bao ji | nu4 fa4 chong1 guan1 bao4 ji1 |  |
| 969 | 三重灾祸 | san chong zai huo | san1 chong2 zai1 huo4 |  |
| 1058 | 像海螺一样卷卷的 | xiang hai luo yi yang juan juan de | xiang4 hai3 luo2 yi1 yang4 juan3 juan3 de5 | 卷卷的 = juǎn juǎn de（卷曲）；不读 juàn |
| 1094 | 双人……是指那种双人吗？ | shuang ren shi zhi na zhong shuang ren ma | shuang1 ren2 shi4 zhi3 na4 zhong3 shuang1 ren2 ma5 | 标点不注音：……？ |
| 1140 | 我得狠狠揍你这家伙一下才行 | wo dei hen hen zou ni zhe jia huo yi xia cai xing | wo3 dei3 hen3 hen3 zou4 ni3 zhe4 jia1 huo5 yi1 xia4 cai2 xing2 | 我得 = wǒ děi（必须）；不读 dé |
| 1141 | 得活着才能是塔克斯 | dei huo zhe cai neng shi ta ke si | dei3 huo2 zhe5 cai2 neng2 shi4 ta3 ke4 si1 | 得活着 = děi huó zhe（必须）；不读 dé |
| 1152 | 忘却之都 | wang que zhi du | wang4 que4 zhi1 du1 | 之都 = zhī dū（都城）；不读 dōu |
| 1211 | 来吧小猫咪，投入我的怀抱！ | lai ba xiao mao mi tou ru wo de huai bao | lai2 ba5 xiao3 mao1 mi1 tou2 ru4 wo3 de5 huai2 bao4 | 标点不注音：，！ |
| 1212 | 宇宙不是我的对口专业 | yu zhou bu shi wo de dui kou zhuan ye | yu3 zhou4 bu4 shi4 wo3 de5 dui4 kou3 zhuan1 ye4 |  |

## 11. 文件说明

| 文件 | 内容 |
| --- | --- |
| `phrases.tsv` | 1212 条词条逐字注音，含 JSON 备选读音 |
| `chars.tsv` | 唯一汉字汇总：次数、主读音、多音字、来源、误读候选 |
| `override.yaml` | 人工确认覆盖（单字默认、上下文规则、整词确认、误读表） |
| `extract.py` | 可复现提取脚本 |
| `REPORT.md` | 本报告 |

复现：

```bash
pip install pypinyin pyyaml
python extract.py
python extract.py --check   # 自检特殊译名与完整性
```

## 12. 列格式

`phrases.tsv`：

| 列 | 说明 |
| --- | --- |
| `id` | 1..N，稳定 ID |
| `line_no` | dict.txt 原始行号 |
| `phrase` | 原词条，标点原样保留 |
| `han_chars` | 仅汉字，标点剔除 |
| `primary_pinyin` | 无调全拼，空格分隔，仅对应汉字 |
| `per_char_readings` | `字:yin1|yin2`，主读音在前 |
| `alt_readings` | JSON 数组，按汉字位置对齐 |
| `notes` | 覆盖理由、标点、生僻字说明 |
| `primary_tone3` | 数字声调，空格分隔（附加列） |
| `punct_chars` | 该词条出现的标点（附加列） |
| `luna_conflict` | 0/1，最终读音是否与 luna 冲突（附加列） |
| `source` | pypinyin / override / manual-confirmed / fallback（附加列） |

`chars.tsv`：

| 列 | 说明 |
| --- | --- |
| `char` | 唯一汉字 |
| `count` | 在全部词条中的出现次数 |
| `primary` | 语料主读音（tone3） |
| `heteronyms` | pypinyin 全部读音，主读音在前 |
| `source` | pypinyin / luna / terra / manual 组合 |
| `notes` | 主读音差异、语料多读、冲突、生僻字说明 |
| `primary_toneless` | 主读音的无调形式（附加列） |
| `corpus_readings` | 语料内读音分布，如 `chang2:13|zhang3:4`（附加列） |
| `luna_readings` | luna 单字读音集合（附加列） |
| `terra_readings` | terra 单字读音集合（附加列） |
| `misread_candidates` | 允许误读集合（附加列） |
| `pypinyin_luna_conflict` | pypinyin 首选是否与 luna 冲突（附加列） |

