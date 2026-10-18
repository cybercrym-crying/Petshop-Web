var detailModal = document.getElementById("detailProductModal");

detailModal.addEventListener("show.bs.modal", function (event) {
  var d = event.relatedTarget.dataset;
  var form = document.getElementById("updateProductForm");
  var delForm = document.getElementById("deleteProductForm");
  var preview = document.getElementById("detailPhotoPreview");

  form.querySelector('[name="name"]').value = d.name;
  form.querySelector('[name="category"]').value = d.category;
  form.querySelector('[name="selling_price"]').value = d.sellingPrice;
  form.querySelector('[name="purchase_price"]').value = d.purchasePrice;
  form.querySelector('[name="stock"]').value = d.stock;
  form.querySelector('[name="photo"]').value = "";

  form.action = "/product/" + d.id + "/edit/";
  delForm.action = "/product/" + d.id + "/delete/";

  preview.textContent = "Photo";
  if (d.photo) {
    var img = document.createElement("img");
    img.src = d.photo;
    img.alt = d.name;
    preview.textContent = "";
    preview.appendChild(img);
  }
});
