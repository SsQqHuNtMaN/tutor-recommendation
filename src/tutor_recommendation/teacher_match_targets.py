from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TargetConfig:
    key: str
    school_slug: str
    college_slug: str
    school_name: str
    college_name: str
    directory_url: str
    affiliation_keywords: tuple[str, ...]
    dedup_priority: int = 100
    cross_target_overlap_group: str = ""

    @property
    def output_dir(self) -> Path:
        return Path("outputs") / self.school_slug / self.college_slug

    @property
    def output_prefix(self) -> str:
        return f"{self.school_slug}_{self.college_slug}_teacher_match"

    @property
    def first_pass_path(self) -> Path:
        return self.output_dir / f"{self.output_prefix}.xlsx"

    @property
    def output_path(self) -> Path:
        return self.first_pass_path

    @property
    def dblp_path(self) -> Path:
        return self.output_dir / f"{self.output_prefix}_dblp.xlsx"

    @property
    def final_path(self) -> Path:
        return self.output_dir / f"{self.output_prefix}_full_research.xlsx"

    @property
    def affiliation_env(self) -> str:
        return ",".join(self.affiliation_keywords)


TARGETS: dict[str, TargetConfig] = {
    "sjtu_cs": TargetConfig(
        key="sjtu_cs",
        school_slug="sjtu",
        college_slug="cs",
        school_name="上海交通大学",
        college_name="计算机学院",
        directory_url="https://www.cs.sjtu.edu.cn/jiaoshiml.html",
        affiliation_keywords=("shanghai jiao tong", "sjtu"),
    ),
    "sjtu_ai": TargetConfig(
        key="sjtu_ai",
        school_slug="sjtu",
        college_slug="ai",
        school_name="上海交通大学",
        college_name="人工智能学院",
        directory_url="https://soai.sjtu.edu.cn/cn/faculty/zzjs",
        affiliation_keywords=("shanghai jiao tong", "sjtu"),
    ),
    "nju_cs": TargetConfig(
        key="nju_cs",
        school_slug="nju",
        college_slug="cs",
        school_name="南京大学",
        college_name="计算机学院",
        directory_url="https://cs.nju.edu.cn/1651/list.htm",
        affiliation_keywords=("nanjing university", "nju"),
    ),
    "nju_ai": TargetConfig(
        key="nju_ai",
        school_slug="nju",
        college_slug="ai",
        school_name="南京大学",
        college_name="人工智能学院",
        directory_url="https://ai.nju.edu.cn/people/list.htm",
        affiliation_keywords=("nanjing university", "nju"),
    ),
    "ruc_gsai": TargetConfig(
        key="ruc_gsai",
        school_slug="ruc",
        college_slug="gsai",
        school_name="中国人民大学",
        college_name="高瓴人工智能学院",
        directory_url="https://gsai.ruc.edu.cn/addons/teacher/index.html",
        affiliation_keywords=("renmin university", "ruc", "gaoling", "gaoling school of artificial intelligence"),
    ),
    "ruc_ssai": TargetConfig(
        key="ruc_ssai",
        school_slug="ruc",
        college_slug="ssai",
        school_name="中国人民大学",
        college_name="苏州人工智能学院",
        directory_url="http://sc.ruc.edu.cn/department/ssai/ssai_users/index.htm",
        affiliation_keywords=("renmin university", "ruc", "suzhou"),
    ),
    "ruc_info": TargetConfig(
        key="ruc_info",
        school_slug="ruc",
        college_slug="info",
        school_name="中国人民大学",
        college_name="信息学院",
        directory_url="http://info.ruc.edu.cn/jsky/szdw/ajxjgcx/bx/bx1/index.htm",
        affiliation_keywords=("renmin university", "ruc", "school of information", "information school"),
    ),
    "nju_ra": TargetConfig(
        key="nju_ra",
        school_slug="nju",
        college_slug="ra",
        school_name="南京大学",
        college_name="机器人与自动化学院",
        directory_url="https://ra.nju.edu.cn/szll/zzjs/index.html",
        affiliation_keywords=("nanjing university", "nju"),
    ),
    "nju_is": TargetConfig(
        key="nju_is",
        school_slug="nju",
        college_slug="is",
        school_name="南京大学",
        college_name="智能科学与技术学院",
        directory_url="https://is.nju.edu.cn/57159/list.htm",
        affiliation_keywords=("nanjing university", "nju"),
    ),
    "nju_ic": TargetConfig(
        key="nju_ic",
        school_slug="nju",
        college_slug="ic",
        school_name="南京大学",
        college_name="集成电路学院",
        directory_url="https://ic.nju.edu.cn/56606/list.htm",
        affiliation_keywords=("nanjing university", "nju"),
    ),
    "fudan_ciram": TargetConfig(
        key="fudan_ciram",
        school_slug="fudan",
        college_slug="ciram",
        school_name="复旦大学",
        college_name="智能机器人与先进制造创新学院",
        directory_url="https://ciram.fudan.edu.cn/cslm/list.htm",
        affiliation_keywords=("fudan university", "fudan"),
        dedup_priority=20,
    ),
    "fudan_ai": TargetConfig(
        key="fudan_ai",
        school_slug="fudan",
        college_slug="ai",
        school_name="复旦大学",
        college_name="计算与智能创新学院",
        directory_url="https://ai.fudan.edu.cn/53161/list.htm",
        affiliation_keywords=("fudan university", "fudan"),
        dedup_priority=40,
    ),
    "seu_cse": TargetConfig(
        key="seu_cse",
        school_slug="seu",
        college_slug="cse",
        school_name="东南大学",
        college_name="计算机科学与工程学院",
        directory_url="https://cse.seu.edu.cn/dsxx/list.htm",
        affiliation_keywords=("southeast university", "seu"),
        dedup_priority=20,
        cross_target_overlap_group="seu_computing_colleges",
    ),
    "seu_software": TargetConfig(
        key="seu_software",
        school_slug="seu",
        college_slug="software",
        school_name="东南大学",
        college_name="软件学院",
        directory_url="https://cse.seu.edu.cn/dsxx/list.htm",
        affiliation_keywords=("southeast university", "seu"),
        dedup_priority=30,
        cross_target_overlap_group="seu_computing_colleges",
    ),
    "seu_ai": TargetConfig(
        key="seu_ai",
        school_slug="seu",
        college_slug="ai",
        school_name="东南大学",
        college_name="人工智能学院",
        directory_url="https://cse.seu.edu.cn/dsxx/list.htm",
        affiliation_keywords=("southeast university", "seu"),
        dedup_priority=40,
        cross_target_overlap_group="seu_computing_colleges",
    ),
    "tongji_cs": TargetConfig(
        key="tongji_cs",
        school_slug="tongji",
        college_slug="cs",
        school_name="同济大学",
        college_name="计算机科学与技术学院",
        directory_url="https://cs.tongji.edu.cn/szdw/jsml_azc_.htm",
        affiliation_keywords=("tongji university", "tongji"),
    ),
    "tongji_see": TargetConfig(
        key="tongji_see",
        school_slug="tongji",
        college_slug="see",
        school_name="同济大学",
        college_name="电子与信息工程学院",
        directory_url="https://see.tongji.edu.cn/szdw1/jzyg/jiaoshou/A_G.htm",
        affiliation_keywords=("tongji university", "tongji"),
    ),
    "zju_cs": TargetConfig(
        key="zju_cs",
        school_slug="zju",
        college_slug="cs",
        school_name="浙江大学",
        college_name="计算机科学与技术学院",
        directory_url="http://www.cs.zju.edu.cn/csen/27003/list.htm",
        affiliation_keywords=("zhejiang university", "zju"),
        dedup_priority=60,
    ),
    "zju_ai": TargetConfig(
        key="zju_ai",
        school_slug="zju",
        college_slug="ai",
        school_name="浙江大学",
        college_name="人工智能学院",
        directory_url="https://ai.zju.edu.cn/90206/list.htm",
        affiliation_keywords=("zhejiang university", "zju"),
        dedup_priority=20,
    ),
    "ustc_ai_ds": TargetConfig(
        key="ustc_ai_ds",
        school_slug="ustc",
        college_slug="ai_ds",
        school_name="中国科学技术大学",
        college_name="人工智能与数据科学学院",
        directory_url=(
            "https://faculty.ustc.edu.cn/xyjslb.jsp?"
            "urltype=tsites.CollegeTeacherList&wbtreeid=1014&st=0&id=1155&lang=zh_CN"
        ),
        affiliation_keywords=(
            "university of science and technology of china",
            "ustc",
            "ai and data science",
        ),
    ),
    "zju_uiuc": TargetConfig(
        key="zju_uiuc",
        school_slug="zju",
        college_slug="uiuc",
        school_name="浙江大学",
        college_name="浙江大学-伊利诺伊大学厄巴纳香槟校区联合学院",
        directory_url="https://zjui.intl.zju.edu.cn/team/teacher",
        affiliation_keywords=("zhejiang university", "zju", "zjui", "university of illinois", "uiuc"),
        dedup_priority=30,
    ),
    "zju_cse": TargetConfig(
        key="zju_cse",
        school_slug="zju",
        college_slug="cse",
        school_name="浙江大学",
        college_name="控制科学与工程学院",
        directory_url="http://www.cse.zju.edu.cn/39568/list.htm",
        affiliation_keywords=("zhejiang university", "zju"),
        dedup_priority=20,
    ),
}


def get_target(key: str) -> TargetConfig:
    try:
        return TARGETS[key]
    except KeyError as exc:
        raise SystemExit(f"Unknown target {key!r}. Available: {', '.join(TARGETS)}") from exc
