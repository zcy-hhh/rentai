# -*- coding: utf-8 -*-
# 作者：zcy
"""构造多模态文档知识库的示例语料：PDF×3 + Excel + PPT，输出到 docs/knowledge_samples/。

可复现：改动本文档内容后重跑即可重新生成全部样例。
"""
from __future__ import annotations

import os

import fitz  # pymupdf 生成 PDF

OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "knowledge_samples")


def write_pdf(name: str, pages: list[str]) -> str:
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        rect = fitz.Rect(50, 40, page.rect.width - 50, page.rect.height - 40)
        page.insert_textbox(rect, text, fontname="china-s", fontsize=10.5, align=3)
    doc.save(path)
    doc.close()
    return path


def write_xlsx(name: str, sheets: dict) -> str:
    import openpyxl

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for sheet_name, header_rows in sheets.items():
        ws = wb.create_sheet(sheet_name)
        for row in header_rows:
            ws.append(row)
    wb.save(path)
    return path


def write_pptx(name: str, slides: list[str]) -> str:
    from pptx import Presentation

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    prs = Presentation()
    for text in slides:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = text.splitlines()[0][:20]
        box = slide.shapes.placeholders[1]
        box.text = text
    prs.save(path)
    return path


# ---------- 1) 租房政策要点 PDF ----------
policy_pages = [
    "《租房政策要点》\n\n一、租赁备案登记\n通过平台或自行成交的租赁，应自签订合同之日起 30 日内办理房屋租赁备案登记。\n"
    "备案需提交：租赁合同、出租人房屋权属证明、承租人身份证明。\n备案后，承租人可凭备案凭证办理居住证、公积金提取等事项。\n"
    "未备案不必然导致合同无效，但可能影响承租人办理居住登记与公共事务。",
    "二、公积金租房提取\n租住商品房的职工，可按月提取住房公积金支付房租。\n"
    "提取条件：连续足额缴存满 3 个月，本人及配偶在本市无自有住房且正在租房。\n"
    "提取额度一般不高于实际租金，且有年度限额。\n办理渠道：公积金中心柜台、线上服务大厅。",
    "三、群租与居住安全治理\n出租住房应以原设计房间为最小出租单位，不得擅自改变房屋内部布局出租。\n"
    "厨房、卫生间、阳台、地下室不得出租供人员居住。\n人均承租建筑面积不得低于规定标准（一般不低于 5 平方米）。\n"
    "违反群租治理规定的，出租人将被责令限期整改并可能面临行政处罚。",
    "四、民用水电与押金\n出租人不得擅自提高水电费单价或按商业标准计收民用水电。\n"
    "押金（保证金）一般不超过一个月租金，退租时应无息返还，扣除款项需双方确认。\n"
    "涉及房屋租赁纠纷，可通过社区调解、房管部门投诉、仲裁或诉讼等途径解决。",
]
pdf1 = write_pdf("租房政策要点.pdf", policy_pages)

# ---------- 2) 租赁合同避坑指南 PDF ----------
contract_pages = [
    "《租赁合同避坑指南》\n\n一、押金与违约金\n签约前应写清押金数额、退还条件与时限。\n"
    "警惕“高额押金+模糊退还条款”：退租时以“墙面损坏”“清洁费”等名义扣光押金。\n"
    "违约金应约定明确比例，避免“提前退租赔三个月租金”这类显失公平条款。\n",
    "二、转租与续租\n未经出租人书面同意，承租人不得擅自转租。\n"
    "转租应签订书面转租协议，并明确转租期不超过原合同剩余租期。\n"
    "续租应提前 15-30 天确认，避免临时加价或到期被要求搬离。\n",
    "三、维修责任与中介费\n房屋及主要设备（水电、门窗、热水器）的维修责任，法律上一般由出租人承担。\n"
    "合同中应明确“谁负责维修、费用谁出”，避免入住后维修纠纷。\n"
    "中介费（服务费）应明确比例与承担方，谨防“看房费”“带看费”等隐形收费。\n",
    "四、虚假房源识别\n对明显低于市场价的“超低价”“急租”“特价”房源保持警惕。\n"
    "签约前核实房屋权属、出租人身份，拒绝“先交定金再看房”。\n"
    "正规中介与平台应能提供核验信息；无法核实的一律视为高风险。\n",
]
pdf2 = write_pdf("租赁合同避坑指南.pdf", contract_pages)

# ---------- 3) 居住安全与群租认定 PDF ----------
safety_pages = [
    "《居住安全与群租认定》\n\n一、群租的主要认定标准\n"
    "将一套住房分割成多个独立房间分别出租，或擅自改变房屋结构（如增加隔断）进行出租，属群租。\n"
    "同一住宅人均承租建筑面积低于 5 平方米，或每个房间居住超过 2 人（且有合理居住需要的除外）。\n"
    "厨房、卫生间、阳台、地下储藏室等非居住空间改为居住用途。\n",
    "二、群租的风险\n群租存在用电过载、消防通道堵塞、治安管理等隐患，易发生安全事故。\n"
    "租住群租房一旦被查，承租人可能面临清退且押金难退。\n"
    "如发现疑似群租，应及时通过物业、社区或 12345 渠道反映。\n",
    "三、商水商电与公寓性质\n商业公寓（公寓性质）通常按商业标准计收水费、电费，月生活成本可能显著高于民用。\n"
    "签约前应问清水电计价性质，估算月成本是否可接受。\n"
    "合同应写明水电单价及计费方式，避免入住后按商业价补缴。\n",
    "四、采光、楼层与通勤\n朝北房源采光差、冬季阴冷，看房时应实际感受采光。\n"
    "无电梯高楼层对老人、小孩及搬运不便。\n距地铁/公交较远会增加通勤成本，签约前应实测通勤时间。\n",
]
pdf3 = write_pdf("居住安全与群租认定.pdf", safety_pages)

# ---------- 4) 区域租金行情 Excel ----------
rent_xlsx = write_xlsx(
    "区域租金行情.xlsx",
    {
        "滨湖区": [
            ["小区", "户型", "月租(元)", "面积(m2)", "备注"],
            ["震泽一村", "1室", 2000, 40, "近地铁"],
            ["太湖新城安置房", "2室", 3200, 75, "装修好"],
            ["滨湖万达周边", "1室", 2500, 48, "商圈"],
            ["蠡湖新城", "3室", 4500, 110, "高档"],
        ],
        "新吴区": [
            ["小区", "户型", "月租(元)", "面积(m2)", "备注"],
            ["金地小区", "1室", 1057, 35, "近地铁"],
            ["梅村公寓", "2室", 2800, 70, "近产业园"],
            ["鸿山片区", "2室", 2600, 80, "近软件园"],
        ],
        "梁溪区": [
            ["小区", "户型", "月租(元)", "面积(m2)", "备注"],
            ["市中心老小区", "1室", 1800, 38, "老城区"],
            ["崇安寺附近", "2室", 3500, 85, "核心商圈"],
        ],
    },
)

# ---------- 5) 滨湖小区介绍 PPT ----------
ppt = write_pptx(
    "滨湖·蠡湖新城小区介绍.pptx",
    [
        "蠡湖新城小区\n户型以 2-3 室为主，绿化率高，临近蠡湖，适合注重居住品质的租客。",
        "户型与租金\n2 室约 110m2，月租 4500 元；3 室约 130m2，月租 5800 元，精装全配。",
        "周边配套\n3 公里内：蠡湖公园、无锡大剧院、地铁 4 号线蠡湖新城站；商超齐全。",
        "物业与费用\n物业费 2.5 元/m2/月；水电为民用标准；车位充足。",
    ],
)

print("生成完成：")
for p in [pdf1, pdf2, pdf3, rent_xlsx, ppt]:
    print(" -", os.path.abspath(p))
