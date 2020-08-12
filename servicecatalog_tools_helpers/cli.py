# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import click
import os
from pathlib import Path
from cloudformation_docs import sdk
from cfn_tools import load_yaml, dump_yaml
import json
import yaml
import re

import collections
from copy import deepcopy



HOME_REGION = os.environ.get(
    "AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")
)


def merge(dict1, dict2):
    result = deepcopy(dict1)
    for key, value in dict2.items():
        if isinstance(value, collections.Mapping):
            result[key] = merge(result.get(key, {}), value)
        else:
            result[key] = deepcopy(dict2[key])
    return result


@click.group()
def cli():
    pass


@cli.command()
@click.argument("p", type=click.Path(exists=True))
@click.argument("owner")
@click.argument("distributor")
@click.argument("support_description")
@click.argument("support_email")
@click.argument("support_url")
@click.argument("tags")
@click.argument("portfolio")
@click.argument("deploy_to_regions")
@click.argument("deploy_to_tags")
def make_product_set(
        p,
        owner,
        distributor,
        support_description,
        support_email,
        support_url,
        tags,
        portfolio,
        deploy_to_regions,
        deploy_to_tags,
):
    products = list()
    launches = dict()
    lookups = {}

    product_set = os.path.basename(p)

    for product in Path(p).iterdir():
        if product.is_dir():
            click.echo(f"Starting product: {product}")
            product_name = os.path.basename(product)
            versions = list()
            product_details = dict(
                Name=product_name,
                Owner=owner,
                Description=product_name,
                Distributor=distributor,
                SupportDescription=support_description,
                SupportEmail=support_email,
                SupportUrl=support_url,
                Source=dict(
                    Provider="CodeCommit",
                    Configuration=dict(RepositoryName=product_name),
                ),
                Versions=versions,
                Tags=json.loads(tags),
            )
            products.append(product_details)
            for version in product.iterdir():
                if version.is_dir():
                    version_name = os.path.basename(version)
                    click.echo(f"Starting version: {version_name}")
                    yaml_file = version / "product.template.yaml"
                    json_file = version / "product.template.json"
                    if yaml_file.is_file():
                        doc = yaml_file.open().read()
                        y = load_yaml(doc)
                        d = y.get("Description")
                        match = re.findall(r"{.+[:,].+}|\[.+[,:].+\]", d)
                        json_string = ""
                        if match:
                            json_string = match[0]
                            d = d.replace(json_string, "")
                        d = d.strip()

                        result = sdk.generate_from_yaml(doc.replace(json_string, ""), product_name)

                        open(version / "README.md", "w").write(result)
                        versions.append(
                            dict(
                                Name=version_name,
                                Description=d,
                                Source=dict(Configuration=dict(BranchName=version_name), ),
                            )
                        )

                        launches[product_name] = dict(
                            portfolio=portfolio,
                            product=product_name,
                            version=version_name,
                            deploy_to=dict(tags=[dict(regions=deploy_to_regions, tag=deploy_to_tags)])
                        )

                        outputs = []
                        for output_name, output_details in y.get('Outputs', {}).items():
                            outputs.append(dict(param_name=f"/{product_set}/{product_name}/{output_name}",
                                                stack_output=output_name))
                            lookups[output_name] = {"param_name": f"/{product_set}/{product_name}/{output_name}",
                                                    "product_name": product_name}
                        if len(outputs) > 0:
                            launches[product_name]['outputs'] = dict(ssm=outputs)

                        meta = json.dumps(
                            {
                                "framework": "servicecatalog-products",
                                "role": "product",
                                "product-set": product_set,
                                "product": product_name,
                                "version": version_name,
                            }
                        )

                        new_description = d.replace("\n", "").replace("\r", "") + "\n" + meta
                        new_description = ''.join('    ' + line for line in new_description.splitlines(True))

                        new_doc = re.sub(
                            r"^Description:((.|\s)*?)^$",
                            f"Description: |\n{new_description} \n",
                            doc,
                            flags=re.MULTILINE,
                        )
                        open(yaml_file, 'w').write(new_doc)

                    elif json_file.is_file():
                        doc = json_file.open().read()
                        j = json.loads(doc)
                        d = j.get("Description")
                        match = re.findall(r"{.+[:,].+}|\[.+[,:].+\]", d)
                        if match:
                            d = d.replace(match[0], "")
                        d = d.strip()
                        result = sdk.generate_from_json(doc, product_name)
                        open(version / "README.md", "w").write(result)
                        versions.append(
                            dict(
                                Name=version_name,
                                Description=d,
                                Source=dict(Configuration=dict(BranchName=version_name), ),
                            )
                        )
                    else:
                        raise Exception("Did not file a template file")

    for product in Path(p).iterdir():
        if product.is_dir():
            click.echo(f"Starting product: {product}")
            product_name = os.path.basename(product)
            for version in product.iterdir():
                if version.is_dir():
                    version_name = os.path.basename(version)
                    click.echo(f"Starting version: {version_name}")
                    yaml_file = version / "product.template.yaml"
                    json_file = version / "product.template.json"
                    if yaml_file.is_file():
                        doc = yaml_file.open().read()
                        y = load_yaml(doc)

                        parameters = {}
                        for parameter_name, parameter_details in y.get('Parameters', {}).items():
                            if lookups.get(parameter_name) is not None:
                                parameters[parameter_name] = {
                                    "ssm": dict(name=lookups.get(parameter_name).get('param_name'))
                                }
                                if launches[product_name].get('depends_on') is None:
                                    launches[product_name]['depends_on'] = list()
                                launches[product_name]['depends_on'].append(lookups.get(parameter_name).get('product_name'))

                            else:
                                parameters[parameter_name] = {
                                    "default": parameter_details.get('Default', "SET_ME")
                                }
                        if len(parameters.keys()) > 0:
                            launches[product_name]['parameters'] = parameters

    portfolios_yaml = Path(p) / "portfolio.yaml"
    portfolios_yaml.open("w").write(
        yaml.safe_dump(
            {"Schema": "factory-2019-04-01", "Portfolios": {"Products": products}}
        )
    )
    manifest_yaml = Path(p) / "manifest.yaml"
    manifest_yaml.open("w").write(
        yaml.safe_dump(
            {"schema": "puppet-2019-04-01", "launches": launches}
        )
    )


@cli.command()
@click.argument("target_portfolio_yaml", type=click.File())
@click.argument("portfolio_name", default=None)
@click.argument("source_product_set", type=click.Path())
def import_product_set(target_portfolio_yaml, portfolio_name, source_product_set):
    source_portfolio = yaml.safe_load(target_portfolio_yaml.read())
    target = None
    if portfolio_name is None:
        if source_portfolio.get("Products") is None:
            source_portfolio.get["Products"] = {}
        target = source_portfolio.get["Products"]
    else:
        if source_portfolio.get("Portfolios") is None:
            source_portfolio["Portfolios"] = []
        for p in source_portfolio.get("Portfolios"):
            if p.get("DisplayName") == portfolio_name:
                if p.get("Products"):
                    target = p.get("Products")
                elif p.get("Components"):
                    target = p.get("Components")
                else:
                    target = p["Products"] = []
        if target is None:
            p = {
                "DisplayName": portfolio_name,
                "Products": [],
            }
            target = p.get("Products")
            source_portfolio["Portfolios"].append(p)

    portfolio_segment = yaml.safe_load(open(Path(source_product_set) / 'portfolio.yaml').read())
    products = portfolio_segment.get("Portfolios").get(
        "Components", []
    ) + portfolio_segment.get("Portfolios").get("Products", [])
    for product in products:
        target.append(product)
        for version in product.get("Versions"):

            source = merge(product.get("Source"), version.get("Source"))

            if source.get("Provider") == "CodeCommit":

                configuration = source.get("Configuration")
                branch_name = configuration.get("BranchName")
                repository_name = configuration.get("RepositoryName")

                os.system(
                    f"aws codecommit create-repository --repository-name {repository_name}"
                )
                command = (
                    "git clone "
                    "--config 'credential.helper=!aws codecommit credential-helper $@' "
                    "--config 'credential.UseHttpPath=true' "
                    f"https://git-codecommit.{HOME_REGION}.amazonaws.com/v1/repos/{repository_name}"
                )
                os.system(command)

                os.system(f"rm -rf {repository_name}/*")

                os.system(f"cp -r {source_product_set}/{product.get('Name')}/{version.get('Name')}/* {repository_name}/")

                if branch_name == "master":
                    os.system(
                        f"cd {repository_name} && git add . && git commit -am 'initial add' && git push"
                    )
                else:
                    os.system(
                        f"cd {repository_name} && git checkout -b {branch_name} && git add . && git commit -am 'initial add' && git push --set-upstream origin {branch_name}"
                    )

                os.system(f"rm -rf {repository_name}")

    with open(target_portfolio_yaml.name, "w") as f:
        f.write(yaml.safe_dump(source_portfolio))



if __name__ == "__main__":
    cli()
